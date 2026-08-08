"""Pydantic schema cho API /classify — theo thiết kế: payload 6 trường + PDF."""

from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentPayload(BaseModel):
    """6 trường thông tin văn bản đến."""

    so_van_ban: str = Field(default="", description="Số hiệu văn bản, vd: 1234/SNNMT-TNN")
    loai_van_ban: str = Field(default="", description="Loại văn bản, vd: Công văn, Quyết định, Chỉ thị…")
    co_quan_ban_hanh: str = Field(default="", description="Cơ quan ban hành văn bản")
    nguoi_ky: str = Field(default="", description="Người ký")
    ngay_van_ban: str = Field(default="", description="Ngày văn bản (YYYY-MM-DD)")
    trich_yeu: str = Field(default="", description="Trích yếu văn bản")


class Recipient(BaseModel):
    """Một cơ quan/lãnh đạo được định tuyến."""

    ten: str
    vai_tro: str = "xử lý chính"  # xử lý chính | phối hợp | theo dõi | bút phê trước
    muc_uu_tien: int = 1
    nguon: str = Field(default="", description="Rule id hoặc 'llm' sinh ra người nhận này")


class MatchedRule(BaseModel):
    rule_id: str
    name: str
    confidence: float = 1.0
    reason: str = ""


class ClassifyResponse(BaseModel):
    job_id: str
    method: str  # rule_engine | llm_reasoning | hybrid
    confidence: float
    recipients: List[Recipient]
    matched_rules: List[MatchedRule]
    reasoning: str = ""
    metadata_verified: Optional[bool] = None
    metadata_notes: List[str] = []
    needs_human_review: bool = False
    warning: Optional[str] = None
    llm_reasoning_preview: Optional[str] = Field(
        default=None, description="Phần reasoning_content của deepseek-reasoner (đã cắt ngắn)"
    )


class HealthResponse(BaseModel):
    status: str
    model: str
    llm_available: bool
    allow_llm: bool
    rule_conf_high: float
    rule_conf_low: float


class AuditEntry(BaseModel):
    id: int
    created_at: str
    job_id: str
    method: str
    confidence: float
    recipients: str
    matched_rules: str
    reasoning: str
    metadata_verified: Optional[bool] = None
    needs_human_review: bool = False
    warning: Optional[str] = None
