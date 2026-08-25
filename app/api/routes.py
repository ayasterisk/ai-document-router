"""API routes — POST /classify nhận 6 field (+ hạn xử lý) + file PDF."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile

from app.models.schema import Assignment, ClassifyResponse
from app.pdf.extractor import extract_pdf_content_bytes
from app.rules.engine import Document
from app.storage import audit

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
async def classify(
    request: Request,
    so_hieu: str = Form(..., description="Số hiệu văn bản"),
    loai: str = Form(..., description="Loại văn bản"),
    co_quan_ban_hanh: str = Form(..., description="Cơ quan ban hành"),
    nguoi_ky: str = Form(..., description="Người ký"),
    ngay_van_ban: date = Form(..., description="Ngày văn bản (YYYY-MM-DD)"),
    trich_yeu: str = Form(..., description="Trích yếu văn bản"),
    han_xu_ly: Optional[date] = Form(None, description="Hạn xử lý (nullable)"),
    file: UploadFile = File(..., description="File PDF đính kèm"),
) -> ClassifyResponse:
    data = await file.read()
    noi_dung = extract_pdf_content_bytes(data)

    doc = Document(
        so_hieu=so_hieu,
        loai=loai,
        co_quan_ban_hanh=co_quan_ban_hanh,
        nguoi_ky=nguoi_ky,
        ngay_van_ban=ngay_van_ban,
        trich_yeu=trich_yeu,
        han_xu_ly=han_xu_ly,
        noi_dung=noi_dung,
    )

    harness = request.app.state.harness
    result = harness.run(doc)

    job_id = uuid.uuid4().hex
    audit.log(job_id, doc, result)

    return ClassifyResponse(
        job_id=job_id,
        assignments=[Assignment(**a) for a in result.assignments],
        confidence=result.confidence,
        reason=result.reason,
        matched_rules=result.matched_rules,
        needs_review=result.needs_review,
        degraded=result.degraded,
        tier=result.tier,
        extracted=result.extracted,
    )


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
