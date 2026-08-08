"""Harness — điều phối pipeline định tuyến (theo doc/thiet-ke-ai-document-router.md):

  1. verify_metadata      — đối chiếu 6 trường payload với nội dung PDF.
  2. rule_engine.apply    — chạy rule cứng deterministic trước.
  3. deepseek-reasoner    — suy luận phần rule không match rõ (không dùng RAG,
                            rulebase được nạp thẳng vào context).
  4. explain_decision     — sinh lý do routing để admin audit.
  5. audit log (SQLite).

Nguyên tắc confidence:
  - >= RULE_CONFIDENCE_HIGH (0.80): chốt kết quả rule engine, không gọi LLM.
  - (LOW, HIGH): gọi LLM kiểm tra/hiệu chỉnh (hybrid).
  - <= LOW (0.50): gọi LLM suy luận từ đầu (llm_reasoning).
  - Không có API key / ALLOW_LLM=0: trả kết quả rule + cờ needs_human_review.
"""

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.llm.client import DeepSeekClient, extract_json
from app.models.schema import ClassifyResponse, DocumentPayload, MatchedRule, Recipient
from app.rules.engine import EngineResult, RuleEngine, RuleMatch, vn_normalize
from app.storage.audit import AuditStore

SYSTEM_PROMPT = """Bạn là trợ lý định tuyến văn bản hành chính của Sở Nông nghiệp và Môi trường (NN&MT) tỉnh Gia Lai.

Nhiệm vụ: dựa trên 6 trường thông tin văn bản + nội dung PDF + rulebase đính kèm, xác định danh sách cơ quan/lãnh đạo chịu trách nhiệm tiếp nhận và xử lý văn bản ĐẾN.

Tuân thủ "Nguyên tắc áp dụng" của rulebase theo đúng thứ tự ưu tiên:
1. Ngoại lệ đặc biệt (Mục IV)
2. Văn bản khẩn — còn 1-2 ngày hạn (Mục V): chuyển SONG SONG lãnh đạo + đơn vị
3. Giấy mời / nội dung như giấy mời (Mục II.4)
4. Văn bản "Giao Sở NN&MT chủ trì" hoặc "Thông báo kết luận UBND, HĐND tỉnh" (Mục I, II.1): LUÔN qua Giám đốc Sở bút phê trước
5. Quy tắc chung theo nguồn gửi (Mục II.1-II.3) + lĩnh vực phụ trách của từng lãnh đạo (Mục III)

Khi xác định lĩnh vực, dùng BẢNG TRA CỨU LĨNH VỰC PHỤ TRÁCH (Mục III) và "Từ điển lĩnh vực" (few-shot kèm ví dụ trích yếu thật) để suy luận ngữ nghĩa khi từ khóa không khớp thẳng.

PHẢN HỒI: chỉ trả về một đối tượng JSON hợp lệ (không markdown, không giải thích ngoài JSON) có cấu trúc:
{
  "recipients": [
    {"ten": "Tên lãnh đạo/cơ quan/đơn vị", "vai_tro": "xử lý chính | phối hợp | theo dõi | bút phê trước", "muc_uu_tien": 1}
  ],
  "confidence": 0.0,
  "matched_rules": [{"rule_id": "...", "name": "...", "reason": "..."}],
  "reasoning": "Giải thích ngắn gọn bằng tiếng Việt tại sao chọn những người nhận này",
  "needs_human_review": false
}
Ghi chú: confidence 0-1. Nếu không đủ thông tin để chốt, trả confidence thấp (<0.5) và needs_human_review=true."""


class Harness:
    def __init__(
        self,
        engine: Optional[RuleEngine] = None,
        llm: Optional[DeepSeekClient] = None,
        audit: Optional[AuditStore] = None,
    ):
        self.engine = engine or RuleEngine()
        self.llm = llm or DeepSeekClient()
        self.audit = audit or AuditStore(settings.AUDIT_DB_PATH)
        self.trace: List[Dict[str, Any]] = []  # trace pipeline khi route()

    def _trace_event(self, event: str, **details: Any) -> None:
        entry: Dict[str, Any] = {"event": event}
        entry.update(details)
        self.trace.append(entry)

    # ------------------------------------------------------------------
    # 1. verify_metadata
    # ------------------------------------------------------------------
    @staticmethod
    def verify_metadata(payload: DocumentPayload, pdf_text: str) -> Tuple[bool, List[str]]:
        notes: List[str] = []
        if not pdf_text:
            return None, ["Không có nội dung PDF để đối chiếu"]  # type: ignore
        norm = vn_normalize(pdf_text)
        verified = True
        if payload.so_van_ban:
            so = vn_normalize(payload.so_van_ban).replace(" ", "")
            if so and so.split("/")[0] not in norm.replace(" ", ""):
                notes.append("Không tìm thấy số văn bản trong nội dung PDF")
                verified = False
        if payload.nguoi_ky:
            nk = vn_normalize(payload.nguoi_ky)
            if nk and len(nk) >= 3 and nk not in norm:
                notes.append("Không tìm thấy tên người ký trong nội dung PDF")
                verified = False
        if payload.trich_yeu:
            ty = vn_normalize(payload.trich_yeu)[:40]
            if ty and len(ty) >= 10 and ty not in norm:
                notes.append("Trích yếu payload không khớp hoàn toàn với nội dung PDF (có thể khác văn phong)")
                verified = False
        if verified and not notes:
            notes.append("Đối chiếu 6 trường với PDF: khớp")
        return verified, notes

    # ------------------------------------------------------------------
    # 2-3. build prompt + gọi deepseek-reasoner
    # ------------------------------------------------------------------
    def build_llm_prompt(self, payload: DocumentPayload, pdf_text: str) -> str:
        rulebase = _read_optional(settings.RULEBASE_PATH)
        tu_dien = _read_optional(settings.TU_DIEN_PATH)
        rules_yaml = _read_optional(settings.RULES_YAML_PATH)
        pdf_excerpt = (pdf_text or "").strip()
        if len(pdf_excerpt) > settings.PDF_MAX_CHARS:
            pdf_excerpt = pdf_excerpt[: settings.PDF_MAX_CHARS] + "\n...[cắt ngắn]"

        payload_json = payload.model_dump(exclude_none=True)
        return f"""Xác định định tuyến cho văn bản đến sau:

--- PAYLOAD (6 trường) ---
{json.dumps(payload_json, ensure_ascii=False, indent=2)}

--- NỘI DUNG PDF ---
{pdf_excerpt if pdf_excerpt else "(không trích được text — chỉ dựa vào payload)"}

--- RULEBASE (doc/rulebase.md) ---
{rulebase}

--- TỪ ĐIỂN LĨNH VỰC (tu-dien-linh-vuc.yaml) ---
{tu_dien}

--- RULES.YAML (bản máy đọc) ---
{rules_yaml}

Hãy áp dụng rulebase để trả về JSON định tuyến theo đúng cấu trúc đã quy định trong system prompt."""

    def llm_reason(
        self, payload: DocumentPayload, pdf_text: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """Gọi deepseek-reasoner. Trả (json, reasoning_content, error)."""
        user = self.build_llm_prompt(payload, pdf_text)
        content, reasoning, err = self.llm.chat(
            SYSTEM_PROMPT, user, response_format={"type": "json_object"}
        )
        if err:
            return None, reasoning, err
        data = extract_json(content or "")
        if data is None:
            return None, reasoning, "Model không trả về JSON hợp lệ"
        return data, reasoning, None



    # ------------------------------------------------------------------
    # pipeline chính
    # ------------------------------------------------------------------
    def route(
        self,
        payload: DocumentPayload,
        pdf_text: str = "",
        pdf_name: str = "",
        allow_llm: Optional[bool] = None,
    ) -> ClassifyResponse:
        job_id = uuid.uuid4().hex[:12]
        allow_llm = settings.ALLOW_LLM if allow_llm is None else allow_llm

        self.trace = []  # reset trace mỗi lần route
        self._trace_event(
            "start", job_id=job_id, pdf_name=pdf_name, allow_llm=allow_llm,
            model=getattr(self.llm, "model", "N/A"),
            llm_available=self.llm.available,
        )

        meta_ok, meta_notes = self.verify_metadata(payload, pdf_text)
        self._trace_event("verify_metadata", verified=meta_ok, notes=meta_notes)

        engine_res = self.engine.evaluate(payload, pdf_text)
        self._trace_event(
            "rule_engine",
            confidence=engine_res.confidence,
            matched_rules=[r.rule_id for r in engine_res.matched_rules],
            recipients=[r["ten"] for r in engine_res.recipients],
            source_category=engine_res.source_category,
            field_leader=engine_res.field_leader,
            central_directive=engine_res.central_directive,
            urgent=engine_res.urgent,
            engine_trace=self.engine.trace,
        )

        # Bước quyết định: có cần gọi LLM không
        need_llm = False
        if not engine_res.has_match:
            need_llm = True
        elif engine_res.confidence < settings.RULE_CONFIDENCE_HIGH:
            need_llm = True
        self._trace_event(
            "decision",
            need_llm=need_llm,
            rule_confidence=engine_res.confidence,
            high_threshold=settings.RULE_CONFIDENCE_HIGH,
            low_threshold=settings.RULE_CONFIDENCE_LOW,
            llm_available=self.llm.available,
        )

        method = "rule_engine"
        reasoning = _rule_reasoning(engine_res)
        llm_preview = None
        warning = None
        recipients: List[Dict[str, Any]] = [dict(r) for r in engine_res.recipients]
        matched_rules = [as_matched_rule(m) for m in engine_res.matched_rules]
        confidence = engine_res.confidence
        needs_review = (meta_ok is False) or not engine_res.has_match

        if need_llm:
            if not allow_llm:
                warning = "ALLOW_LLM=0 — dừng ở rule engine, cần review thủ công"
                needs_review = True
                self._trace_event("llm_skip", reason="ALLOW_LLM=0")
            elif not self.llm.available:
                warning = "Chưa cấu hình DEEPSEEK_API_KEY — bỏ qua suy luận LLM, cần review thủ công"
                needs_review = True
                self._trace_event("llm_skip", reason="Chưa có DEEPSEEK_API_KEY")
            else:
                self._trace_event(
                    "llm_call",
                    model=getattr(self.llm, "model", "N/A"),
                    reasoning_mode=getattr(self.llm, "reasoning", None),
                )
                llm_json, llm_preview, llm_err = self.llm_reason(payload, pdf_text)
                if llm_err:
                    warning = f"Lỗi gọi deepseek-reasoner: {llm_err}"
                    needs_review = True
                    self._trace_event("llm_error", error=llm_err)
                elif llm_json:
                    method = "llm_reasoning" if not engine_res.has_match else "hybrid"
                    recipients = _normalize_llm_recipients(llm_json)
                    llm_conf = float(llm_json.get("confidence", 0.0))
                    # hybrid: giữ confidence của rule nếu cao hơn (không hạ kết quả rule rõ)
                    confidence = llm_conf if method == "llm_reasoning" else max(confidence, llm_conf)
                    llm_rules = llm_json.get("matched_rules") or []
                    if not engine_res.has_match:
                        matched_rules = _normalize_llm_rules(llm_rules)
                    reasoning = llm_json.get("reasoning", reasoning)
                    needs_review = bool(llm_json.get("needs_human_review", False)) or confidence < 0.5
                    self._trace_event(
                        "llm_ok",
                        method=method,
                        llm_confidence=llm_conf,
                        final_confidence=confidence,
                        recipients=[r["ten"] for r in recipients],
                        matched_rules=[r.rule_id for r in matched_rules],
                        reasoning=reasoning[:200],
                    )

        resp = ClassifyResponse(
            job_id=job_id,
            method=method,
            confidence=round(confidence, 3),
            recipients=[Recipient(**r) for r in recipients],
            matched_rules=matched_rules,
            reasoning=reasoning,
            metadata_verified=meta_ok,
            metadata_notes=meta_notes,
            needs_human_review=needs_review,
            warning=warning,
            llm_reasoning_preview=_shorten(llm_preview, 1500) if llm_preview else None,
        )

        # audit log
        self.audit.insert(
            {
                "job_id": job_id,
                "payload": payload.model_dump(),
                "pdf_name": pdf_name,
                "pdf_chars": len(pdf_text or ""),
                "method": resp.method,
                "confidence": resp.confidence,
                "recipients": [r.model_dump() for r in resp.recipients],
                "matched_rules": [r.model_dump() for r in resp.matched_rules],
                "reasoning": resp.reasoning,
                "metadata_verified": resp.metadata_verified,
                "needs_human_review": resp.needs_human_review,
                "warning": resp.warning,
            }
        )
        self._trace_event(
            "done",
            method=resp.method,
            confidence=resp.confidence,
            recipients=[r.ten for r in resp.recipients],
            needs_human_review=resp.needs_human_review,
            warning=resp.warning,
        )
        return resp


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _read_optional(path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "(không đọc được file)"


def _shorten(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "..."


def as_matched_rule(m: RuleMatch) -> MatchedRule:
    return MatchedRule(rule_id=m.rule_id, name=m.name, confidence=m.confidence, reason=m.reason)


def _rule_reasoning(res: EngineResult) -> str:
    if not res.matched_rules:
        return ""
    return " | ".join(f"[{r.rule_id}] {r.name}: {r.reason}" for r in res.matched_rules)


def _normalize_llm_recipients(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(data.get("recipients") or []):
        if not isinstance(r, dict) or not r.get("ten"):
            continue
        out.append(
            {
                "ten": str(r["ten"]),
                "vai_tro": str(r.get("vai_tro") or "xử lý chính"),
                "muc_uu_tien": int(r.get("muc_uu_tien") or i + 1),
                "nguon": "llm",
            }
        )
    return out


def _normalize_llm_rules(rules: List[Any]) -> List[MatchedRule]:
    out: List[MatchedRule] = []
    for r in rules or []:
        if not isinstance(r, dict):
            continue
        out.append(
            MatchedRule(
                rule_id=str(r.get("rule_id") or "llm"),
                name=str(r.get("name") or "Suy luận deepseek-reasoner"),
                reason=str(r.get("reason") or ""),
                confidence=float(r.get("confidence") or 0.0),
            )
        )
    return out


harness = Harness()
