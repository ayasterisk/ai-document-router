"""Pydantic schema cho response định tuyến văn bản (không còn payload JSON đầu vào)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Tier = Literal["T2", "T1", "T0"]


class ClassifyResponse(BaseModel):
    """Kết quả để chuyển văn bản đi — 4 trường chính + thông tin audit."""

    job_id: str
    # 4 trường kết quả chính
    don_vi_xu_ly_chinh: List[str] = Field(default_factory=list)
    phoi_hop_xu_ly: List[str] = Field(default_factory=list)
    lanh_dao_theo_doi: List[str] = Field(default_factory=list)
    han_thuc_hien: Optional[str] = Field(None, description="ISO date, 'hỏa tốc', hoặc null")
    # thông tin kèm theo
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = ""
    matched_rules: List[str] = Field(default_factory=list)
    needs_review: bool = False
    degraded: bool = False
    tier: Tier = "T0"
    extracted_metadata: Dict[str, Any] = Field(default_factory=dict)
