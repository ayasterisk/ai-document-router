"""Pydantic schemas cho request/response của API phân loại văn bản."""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Role = Literal["xử lý chính", "phối hợp xử lý", "theo dõi"]
Tier = Literal["T2", "T1", "T0"]


class ClassifyRequest(BaseModel):
    """6 trường bắt buộc + 1 trường tùy chọn (hạn xử lý)."""

    so_hieu: str = Field(..., description="Số hiệu văn bản")
    loai: str = Field(..., description="Loại văn bản")
    co_quan_ban_hanh: str = Field(..., description="Cơ quan ban hành")
    nguoi_ky: str = Field(..., description="Người ký")
    ngay_van_ban: date = Field(..., description="Ngày văn bản")
    trich_yeu: str = Field(..., description="Trích yếu văn bản")
    han_xu_ly: Optional[date] = Field(None, description="Hạn xử lý (nullable)")


class Assignment(BaseModel):
    """Một người/đơn vị được phân công, kèm vai trò."""

    role: Role = "xử lý chính"
    target: str = Field(..., description="Tên người/đơn vị đã chuẩn hóa")
    email: Optional[str] = Field(None, description="Email nếu tra được từ danh bạ")


class ClassifyResponse(BaseModel):
    """Response thống nhất cho cả 3 bậc harness (T2/T1/T0)."""

    job_id: str
    assignments: List[Assignment] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = ""
    matched_rules: List[str] = Field(default_factory=list)
    needs_review: bool = False
    degraded: bool = False
    tier: Tier = "T2"
    extracted: Dict[str, Any] = Field(
        default_factory=dict,
        description="Đặc điểm đã nhận diện: nguồn gửi, lĩnh vực, ký hiệu, khẩn...",
    )
