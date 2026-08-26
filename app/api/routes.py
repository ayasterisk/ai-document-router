"""API routes — POST /classify nhận file đính kèm (PDF), không còn payload JSON."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.models.schema import ClassifyResponse
from app.pdf.extractor import extract_pdf_content_bytes
from app.storage import audit

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    request: Request,
    file: Optional[UploadFile] = File(None, description="File đính kèm (thường là PDF)"),
    text: Optional[str] = Form(None, description="Text thô (tùy chọn, để test/dev)"),
) -> ClassifyResponse:
    noi_dung = (text or "").strip()

    if not noi_dung and file is not None:
        data = await file.read()
        if data:
            noi_dung = extract_pdf_content_bytes(data).strip()

    if not noi_dung:
        raise HTTPException(status_code=400, detail="Không trích được nội dung từ file đính kèm.")

    harness = request.app.state.harness
    result = harness.run(noi_dung)

    job_id = uuid.uuid4().hex
    audit.log(job_id, noi_dung, result)

    return ClassifyResponse(
        job_id=job_id,
        don_vi_xu_ly_chinh=result.don_vi_xu_ly_chinh,
        phoi_hop_xu_ly=result.phoi_hop_xu_ly,
        lanh_dao_theo_doi=result.lanh_dao_theo_doi,
        han_thuc_hien=result.han_thuc_hien,
        confidence=result.confidence,
        reason=result.reason,
        matched_rules=result.matched_rules,
        needs_review=result.needs_review,
        degraded=result.degraded,
        tier=result.tier,
        extracted_metadata=result.extracted_metadata,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
