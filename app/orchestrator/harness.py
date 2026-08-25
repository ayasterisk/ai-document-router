"""Harness điều phối: chạy rule engine deterministic trước, chỉ gọi model cho phần "mờ".

Hoạt động theo 3 bậc (xem thiết kế Mục 3.2):
  T2 — model gọi tool (function-calling) qua vòng lặp agent
  T1 — model trả JSON trực tiếp (prompt-only, rule set nằm trong context)
  T0 — không dùng model (chỉ rule engine)

Thang fallback: T2 -> T1 -> T0. Kết quả luôn hợp lệ, kèm cờ `degraded`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from app.rules.engine import Document, RuleEngine

logger = logging.getLogger(__name__)

# Tool mà model (T2) có thể gọi — chính là rule engine deterministic
APPLY_RULES_TOOL = {
    "type": "function",
    "function": {
        "name": "apply_rules",
        "description": "Chạy rule engine định tuyến văn bản và trả kết quả.",
        "parameters": {
            "type": "object",
            "properties": {
                "so_hieu": {"type": "string"},
                "loai": {"type": "string"},
                "co_quan_ban_hanh": {"type": "string"},
                "nguoi_ky": {"type": "string"},
                "ngay_van_ban": {"type": "string"},
                "trich_yeu": {"type": "string"},
                "han_xu_ly": {"type": ["string", "null"]},
                "noi_dung": {"type": "string"},
            },
            "required": ["so_hieu", "co_quan_ban_hanh", "trich_yeu"],
        },
    },
}


# --------------------------------------------------------------------------- #
# Inference client (trừu tượng): mock cho dev, HTTP cho vLLM/TGI thật
# --------------------------------------------------------------------------- #
class InferenceClient:
    supports_tool_calling: bool = False

    def generate(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        raise NotImplementedError


class MockInferenceClient(InferenceClient):
    """Trả response giả lập để phát triển/test không cần GPU (thiết kế Mục 7).

    Lần gọi đầu (nếu có tools) trả tool_call -> apply_rules; các lần sau trả JSON cuối.
    """

    def __init__(self, supports_tool_calling: bool = True) -> None:
        self.supports_tool_calling = supports_tool_calling
        self._calls = 0

    def generate(self, messages, tools=None):
        self._calls += 1
        if tools and self.supports_tool_calling and self._calls == 1:
            return {
                "tool_calls": [
                    {
                        "id": "call_mock_1",
                        "function": {
                            "name": "apply_rules",
                            "arguments": json.dumps(self._extract_args(messages)),
                        },
                    }
                ]
            }
        return {
            "content": json.dumps(
                {
                    "assignments": [{"role": "xử lý chính", "target": "PGĐ Vũ Ngọc An"}],
                    "confidence": 0.7,
                    "reason": "Mock model: suy luận lĩnh vực thủy lợi từ trích yếu.",
                },
                ensure_ascii=False,
            )
        }

    @staticmethod
    def _extract_args(messages) -> Dict[str, Any]:
        # lấy text user cuối cùng làm trích yếu giả lập
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return {
            "so_hieu": "",
            "loai": "",
            "co_quan_ban_hanh": "",
            "nguoi_ky": "",
            "ngay_van_ban": None,
            "trich_yeu": str(last_user)[:200],
            "han_xu_ly": None,
            "noi_dung": "",
        }


class HttpInferenceClient(InferenceClient):
    """Gọi inference server local (vLLM/TGI) qua API tương thích OpenAI."""

    def __init__(self, base_url: str, api_key: str = "EMPTY", supports_tool_calling: bool = True) -> None:
        import httpx  # local import để không bắt buộc cài khi dùng mock

        self._httpx = httpx
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.supports_tool_calling = supports_tool_calling

    def generate(self, messages, tools=None):
        payload: Dict[str, Any] = {"model": "default", "messages": messages, "temperature": 0}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        resp = self._httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
@dataclass
class HarnessResult:
    assignments: List[Dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    matched_rules: List[str] = field(default_factory=list)
    needs_review: bool = False
    degraded: bool = False
    tier: str = "T0"
    extracted: Dict[str, Any] = field(default_factory=dict)


class Harness:
    def __init__(
        self,
        engine: RuleEngine,
        client: Optional[InferenceClient] = None,
        mode: str = "auto",  # auto | native | prompt | off
        max_tool_steps: int = 6,
        retry: int = 2,
    ) -> None:
        self.engine = engine
        self.client = client or MockInferenceClient()
        self.mode = mode
        self.max_tool_steps = max_tool_steps
        self.retry = retry

    # ------------------------------------------------------------------ #
    def run(self, doc: Document, today: Optional[date] = None) -> HarnessResult:
        engine_result = self.engine.run(doc, today)

        # Happy path: rule cứng khớp rõ -> không cần model
        if not engine_result.needs_review:
            return self._from_engine(engine_result, tier="T0", degraded=False)

        # Cần model cho phần "mờ"
        if self.mode == "off":
            return self._from_engine(engine_result, tier="T0", degraded=True)

        # Thử T2 (tool-calling)
        if self.mode in ("auto", "native") and self.client.supports_tool_calling:
            result = self._run_t2(doc)
            if result is not None:
                return result

        # Fallback T1 (prompt-only)
        if self.mode in ("auto", "native", "prompt"):
            result = self._run_t1(doc)
            if result is not None:
                return result

        # Fallback T0
        return self._from_engine(engine_result, tier="T0", degraded=True)

    # ------------------------------------------------------------------ #
    def _from_engine(self, er, tier: str, degraded: bool) -> HarnessResult:
        return HarnessResult(
            assignments=er.assignments,
            confidence=er.confidence,
            reason=er.reason,
            matched_rules=er.matched_rules,
            needs_review=er.needs_review,
            degraded=degraded,
            tier=tier,
            extracted=er.extracted,
        )

    def _run_t2(self, doc: Document) -> Optional[HarnessResult]:
        """Vòng lặp agent: model có thể gọi tool apply_rules."""
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": "Bạn là trợ lý định tuyến văn bản đến của Sở NN&MT. "
                "Khi chưa chắc chắn, hãy gọi tool apply_rules để chạy rule engine.",
            },
            {"role": "user", "content": self._document_prompt(doc)},
        ]

        for _ in range(self.max_tool_steps):
            try:
                raw = self.client.generate(messages, tools=[APPLY_RULES_TOOL])
            except Exception as exc:  # noqa: BLE001
                logger.warning("T2 lỗi gọi model: %s", exc)
                return None

            tool_calls = raw.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    fn = call.get("function", {})
                    if fn.get("name") == "apply_rules":
                        args = json.loads(fn.get("arguments", "{}"))
                        engine_out = self.engine.run(Document(**self._coerce(args)), None)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", "mock"),
                                "content": json.dumps(
                                    {
                                        "assignments": engine_out.assignments,
                                        "needs_review": engine_out.needs_review,
                                        "matched_rules": engine_out.matched_rules,
                                    },
                                    ensure_ascii=False,
                                ),
                            }
                        )
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})
                continue

            # model trả câu trả lời cuối (JSON)
            return self._parse_final(raw.get("content"), tier="T2")

        return None

    def _run_t1(self, doc: Document) -> Optional[HarnessResult]:
        """Prompt-only: gộp toàn bộ rule set vào context, model trả 1 JSON."""
        rule_set = json.dumps(
            {"lookup": self.engine.lookup, "rules": self.engine.rules},
            ensure_ascii=False,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là hệ thống định tuyến văn bản đến. Dưới đây là toàn bộ rule set "
                    "(điều kiện -> cơ quan nhận). Hãy suy luận và trả VỀ ĐÚNG MỘT JSON, "
                    'không kèm text khác, theo cấu trúc: {"assignments":[{"role":"xử lý chính",'
                    '"target":"..."}],"confidence":0.0-1.0,"reason":"..."}.\n\n'
                    f"RULE_SET:\n{rule_set}"
                ),
            },
            {"role": "user", "content": self._document_prompt(doc)},
        ]
        try:
            raw = self.client.generate(messages, tools=None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("T1 lỗi gọi model: %s", exc)
            return None
        return self._parse_final(raw.get("content"), tier="T1")

    # ------------------------------------------------------------------ #
    def _parse_final(self, content: Optional[str], tier: str) -> Optional[HarnessResult]:
        if not content:
            return None
        for _ in range(self.retry + 1):
            try:
                data = json.loads(content)
                return HarnessResult(
                    assignments=[
                        {"role": a.get("role", "xử lý chính"), "target": a["target"]}
                        for a in data.get("assignments", [])
                    ],
                    confidence=float(data.get("confidence", 0.0)),
                    reason=data.get("reason", ""),
                    needs_review=bool(data.get("needs_review", False)),
                    degraded=tier != "T2",
                    tier=tier,
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                # thử bóc phần JSON nằm trong dấu ngoặc nhọn
                start, end = content.find("{"), content.rfind("}")
                if start != -1 and end > start:
                    content = content[start : end + 1]
                else:
                    return None
        return None

    # ------------------------------------------------------------------ #
    @staticmethod
    def _document_prompt(doc: Document) -> str:
        return (
            f"Số hiệu: {doc.so_hieu}\n"
            f"Loại: {doc.loai}\n"
            f"Cơ quan ban hành: {doc.co_quan_ban_hanh}\n"
            f"Người ký: {doc.nguoi_ky}\n"
            f"Ngày văn bản: {doc.ngay_van_ban}\n"
            f"Hạn xử lý: {doc.han_xu_ly or 'null'}\n"
            f"Trích yếu: {doc.trich_yeu}\n"
            f"Nội dung PDF: {doc.noi_dung[:4000]}"
        )

    @staticmethod
    def _coerce(args: Dict[str, Any]) -> Dict[str, Any]:
        """Ép kiểu arguments (chuỗi ngày -> date) trước khi dựng Document."""
        import datetime as _dt

        out = dict(args)
        for key in ("ngay_van_ban", "han_xu_ly"):
            val = out.get(key)
            if isinstance(val, str):
                try:
                    out[key] = _dt.date.fromisoformat(val)
                except ValueError:
                    out[key] = None
        return out
