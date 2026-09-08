"""Validated public contract. Only ISO dates belong in han_thuc_hien."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ROLES = ("don_vi_xu_ly_chinh", "phoi_hop_xu_ly", "lanh_dao_theo_doi")


class RoutingFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    don_vi_xu_ly_chinh: list[str] = Field(default_factory=list, max_length=40)
    phoi_hop_xu_ly: list[str] = Field(default_factory=list, max_length=40)
    lanh_dao_theo_doi: list[str] = Field(default_factory=list, max_length=40)
    han_thuc_hien: str | None = None

    @field_validator(*ROLES)
    @classmethod
    def validate_recipients(cls, values):
        if any(not v.strip() or len(v) > 200 for v in values) or len(values) != len(
            set(values)
        ):
            raise ValueError("Recipients must be nonempty, unique names or IDs")
        return values

    @field_validator("han_thuc_hien")
    @classmethod
    def deadline(cls, value):
        if value is not None and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Expected YYYY-MM-DD")
        return value


class ModelDecision(RoutingFields):
    don_vi_xu_ly_chinh: list[str] = Field(min_length=1, max_length=40)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000)
    needs_review: bool = True


class Recipient(BaseModel):
    id: str
    name: str


class ClassifyResponse(RoutingFields):
    job_id: str
    document_id: str
    input_sha256: str
    rules_version: str
    rules_sha256: str
    directory_version: str
    received_on: date
    confidence: float = Field(0, ge=0, le=1, allow_inf_nan=False)
    confidence_kind: Literal["heuristic_uncalibrated"] = "heuristic_uncalibrated"
    reason: str = ""
    matched_rules: list[str] = Field(default_factory=list)
    needs_review: bool = True
    requires_confirmation: bool = True
    degraded: bool = False
    tier: Literal["T2", "T1", "T0"] = "T0"
    do_khan: Literal["thuong", "khan", "thuong_khan", "hoa_toc"] = "thuong"
    review_reasons: list[str] = Field(default_factory=list)
    extracted_metadata: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    extraction: dict[str, Any] = Field(default_factory=dict)
    recipients: dict[str, list[Recipient]] = Field(default_factory=dict)


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    result: ClassifyResponse | None = None
    error: str | None = None


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: str = Field(min_length=1, max_length=200)
    input_sha256: str
    rules_sha256: str
    decision: Literal["accepted", "edited", "rejected"]
    # Recipient IDs from /v1/directory, never browser option IDs.
    final: RoutingFields | None = None
    do_khan: Literal["thuong", "khan", "thuong_khan", "hoa_toc"] = "thuong"
    note: str = Field("", max_length=2000)
