"""API routes — theo thiết kế: POST /classify nhận 6 trường JSON + file PDF (multipart)."""

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.config import settings
from app.models.schema import AuditEntry, ClassifyResponse, DocumentPayload, HealthResponse
from app.orchestrator.harness import harness
from app.pdf.extractor import extract_text_from_bytes

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model=settings.DEEPSEEK_MODEL,
        llm_available=harness.llm.available,
        allow_llm=settings.ALLOW_LLM,
        rule_conf_high=settings.RULE_CONFIDENCE_HIGH,
        rule_conf_low=settings.RULE_CONFIDENCE_LOW,
    )


@router.get("/rules", tags=["meta"])
def list_rules():
    """Liệt kê rule đang nạp (cho admin đối chiếu với rulebase.md)."""
    rules = harness.engine.rules
    summary = {
        "version": rules.get("version"),
        "nguon": rules.get("nguon"),
        "so_luong": {
            "ngoai_le": len(rules.get("exceptions", [])),
            "khan": len(rules.get("urgent", {}).get("routes", [])),
            "linh_vuc": len(rules.get("field_routes", [])),
        },
        "danh_sach_rule": [
            {"id": e["id"], "name": e["name"], "confidence": e.get("confidence")}
            for e in rules.get("exceptions", [])
        ]
        + [
            {"id": r["id"], "name": "Văn bản khẩn", "confidence": r.get("confidence")}
            for r in rules.get("urgent", {}).get("routes", [])
        ]
        + [
            {"id": fr["id"], "name": f"Lĩnh vực: {fr['lanh_dao']}", "confidence": None}
            for fr in rules.get("field_routes", [])
        ],
    }
    return summary


@router.post("/classify", response_model=ClassifyResponse, tags=["classify"])
async def classify_multipart(
    so_van_ban: str = Form(""),
    loai_van_ban: str = Form(""),
    co_quan_ban_hanh: str = Form(""),
    nguoi_ky: str = Form(""),
    ngay_van_ban: str = Form(""),
    trich_yeu: str = Form(""),
    pdf: Optional[UploadFile] = File(None),
):
    """Nhận 6 trường JSON (form) + file PDF đính kèm (multipart)."""
    payload = DocumentPayload(
        so_van_ban=so_van_ban,
        loai_van_ban=loai_van_ban,
        co_quan_ban_hanh=co_quan_ban_hanh,
        nguoi_ky=nguoi_ky,
        ngay_van_ban=ngay_van_ban,
        trich_yeu=trich_yeu,
    )
    pdf_text, engine_used, need_ocr = "", "", False
    pdf_name = pdf.filename if pdf else None
    if pdf is not None:
        data = await pdf.read()
        if data:
            pdf_text, engine_used, need_ocr = extract_text_from_bytes(data, max_chars=settings.PDF_MAX_CHARS)
        else:
            need_ocr = True

    resp = harness.route(payload, pdf_text=pdf_text, pdf_name=pdf_name or "")

    if need_ocr and not pdf_text:
        resp.warning = (resp.warning + "; " if resp.warning else "") + \
            "PDF có vẻ là bản scan — chưa trích được text, kết quả chỉ dựa trên payload"
        resp.needs_human_review = True
    if engine_used:
        resp.metadata_notes = resp.metadata_notes + [f"PDF extracted by: {engine_used}"]
    return resp


@router.post("/classify/json", response_model=ClassifyResponse, tags=["classify"])
def classify_json(payload: DocumentPayload):
    """Phiên bản JSON thuần (không cần file PDF) — tiện cho test nhanh."""
    resp = harness.route(payload, pdf_text="", pdf_name="")
    if not resp.metadata_verified:
        resp.metadata_notes = ["Không có PDF — không đối chiếu được 6 trường"]
    return resp


@router.get("/audit", tags=["audit"])
def list_audit(limit: int = Query(20, ge=1, le=100)):
    rows = harness.audit.list(limit=limit)
    return [AuditEntry(
        id=r["id"],
        created_at=r["created_at"],
        job_id=r["job_id"],
        method=r["method"],
        confidence=r["confidence"],
        recipients=r["recipients"],
        matched_rules=r["matched_rules"],
        reasoning=r["reasoning"],
        metadata_verified=r["metadata_verified"],
        needs_human_review=r["needs_human_review"],
        warning=r["warning"],
    ) for r in rows]
