"""Test luồng deepseek-reasoner (mock client) — xác nhận tích hợp LLM hoạt động.

Không cần API key thật: dùng FakeLLM trả JSON như deepseek-reasoner.
"""

import json

from app.llm.client import extract_json
from app.models.schema import DocumentPayload
from app.orchestrator.harness import Harness
from app.storage.audit import AuditStore


class FakeLLM:
    available = True

    def __init__(self, content: str, reasoning: str = "fake reasoning"):
        self.content = content
        self.reasoning = reasoning

    def chat(self, system, user, response_format=None, max_tokens=None):
        return self.content, self.reasoning, None


def test_extract_json_tool():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json("xử lý {a: 1}") is None  # không phải JSON hợp lệ
    assert extract_json('{"recipients": []}') == {"recipients": []}


def test_llm_path_no_rule_match(tmp_path):
    payload = DocumentPayload(
        so_van_ban="1/ABC",
        loai_van_ban="Công văn",
        co_quan_ban_hanh="Công ty TNHH ABC",
        nguoi_ky="",
        ngay_van_ban="2026-08-08",
        # KHÔNG chứa keyword lĩnh vực nào -> rule engine không match
        trich_yeu="V/v đề nghị hỗ trợ xúc tiến thương mại, quảng bá sản phẩm nông sản",
    )
    llm_json = {
        "recipients": [
            {"ten": "PGĐ Nguyễn Thị Tố Trân", "vai_tro": "xử lý chính", "muc_uu_tien": 1},
            {"ten": "Chi cục Trồng trọt và BVTV", "vai_tro": "xử lý chính", "muc_uu_tien": 1},
        ],
        "confidence": 0.85,
        "matched_rules": [{"rule_id": "llm", "name": "Suy luận", "reason": "lĩnh vực trồng trọt"}],
        "reasoning": "Nội dung liên quan trồng trọt -> PGĐ Tố Trân",
        "needs_human_review": False,
    }
    fake = FakeLLM(json.dumps(llm_json, ensure_ascii=False))
    harness = Harness(llm=fake, audit=AuditStore(str(tmp_path / "audit.db")))
    resp = harness.route(payload, pdf_text="", pdf_name="")

    assert resp.method == "llm_reasoning"
    assert resp.confidence == 0.85
    assert any("Nguyễn Thị Tố Trân" in r.ten for r in resp.recipients)
    assert resp.llm_reasoning_preview == "fake reasoning"
    assert resp.needs_human_review is False
    # audit đã ghi
    assert harness.audit.get(resp.job_id) is not None


def test_llm_path_malformed_json_falls_back(tmp_path):
    """LLM trả text không phải JSON -> báo warning + cần review, không crash."""
    payload = DocumentPayload(
        so_van_ban="",
        loai_van_ban="Công văn",
        co_quan_ban_hanh="Ban Quản lý dự án",
        nguoi_ky="",
        ngay_van_ban="2026-08-08",
        trich_yeu="V/v đề nghị phối hợp triển khai dự án cộng đồng ven biển",
    )
    fake = FakeLLM("Tôi không chắc chắn lắm nhưng có thể là PGĐ Trần Quốc Khánh...", "thinking...")
    harness = Harness(llm=fake, audit=AuditStore(str(tmp_path / "audit2.db")))
    resp = harness.route(payload, pdf_text="", pdf_name="")

    assert resp.warning and "JSON" in resp.warning
    assert resp.needs_human_review is True


def test_hybrid_path_llm_giu_confidence_rule(tmp_path, monkeypatch):
    """Rule match mờ (dưới ngưỡng HIGH) -> LLM refine, không hạ confidence rule."""
    # Nâng ngưỡng HIGH để trận khớp III.an (conf ~0.88) bị coi là "chưa chắc"
    from app.config import settings

    monkeypatch.setattr(settings, "RULE_CONFIDENCE_HIGH", 0.92)

    payload = DocumentPayload(
        so_van_ban="",  # bỏ số hiệu để không có bonus mã ký hiệu (conf ~0.90)
        loai_van_ban="Công văn",
        co_quan_ban_hanh="Sở Nông nghiệp và Môi trường",
        nguoi_ky="",
        ngay_van_ban="2026-08-08",
        trich_yeu="V/v triển khai thực hiện kế hoạch cấp nước an toàn khu vực nông thôn",
    )
    llm_json = {
        "recipients": [
            {"ten": "PGĐ Vũ Ngọc An", "vai_tro": "xử lý chính", "muc_uu_tien": 1},
            {"ten": "TT Nước sạch nông thôn", "vai_tro": "xử lý chính", "muc_uu_tien": 1},
        ],
        "confidence": 0.9,
        "matched_rules": [],
        "reasoning": "Đồng ý với rule engine",
        "needs_human_review": False,
    }
    fake = FakeLLM(json.dumps(llm_json, ensure_ascii=False))
    harness = Harness(llm=fake, audit=AuditStore(str(tmp_path / "audit3.db")))
    resp = harness.route(payload, pdf_text="", pdf_name="")

    # rule engine match (III.an) nhưng confidence < HIGH -> hybrid
    assert resp.method == "hybrid"
    assert resp.confidence == 0.9  # max(rule ~0.90, llm 0.9)
    assert any("Vũ Ngọc An" in r.ten for r in resp.recipients)
