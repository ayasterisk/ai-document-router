"""Test pipeline (harness) với PDF thật trong source/ — không cần API key.

Chạy:  python -m pytest tests/test_harness.py -v
"""

from pathlib import Path

from app.models.schema import DocumentPayload
from app.orchestrator.harness import Harness
from app.pdf.extractor import extract_text_from_file

SOURCE_DIR = Path(__file__).resolve().parent.parent / "source"


def _first_pdf():
    pdfs = sorted(SOURCE_DIR.glob("*.pdf"))
    assert pdfs, "Không tìm thấy PDF mẫu trong source/"
    return pdfs[0]


def test_extract_pdf_text():
    pdf = _first_pdf()
    text, engine, need_ocr = extract_text_from_file(str(pdf))
    assert need_ocr is False, f"{pdf.name} trích text bị rỗng (bản scan?)"
    assert len(text) > 50


def test_pipeline_rule_path_with_pdf():
    pdf = _first_pdf()
    text, _, _ = extract_text_from_file(str(pdf))
    payload = DocumentPayload(
        so_van_ban=pdf.stem.split("-")[0].strip(),
        loai_van_ban="Công văn",
        co_quan_ban_hanh="Sở Nông nghiệp và Môi trường",
        nguoi_ky="",
        ngay_van_ban="2026-08-05",
        trich_yeu=text[:120].splitlines()[2] if len(text.splitlines()) > 2 else text[:120],
    )
    harness = Harness()
    resp = harness.route(payload, pdf_text=text, pdf_name=pdf.name, allow_llm=False)
    assert resp.job_id
    assert resp.method in ("rule_engine",)
    assert resp.confidence >= 0.0
    # audit đã ghi
    row = harness.audit.get(resp.job_id)
    assert row is not None


def test_pipeline_khong_api_key_flag_review():
    """Không có DEEPSEEK_API_KEY mà rule không match -> cần review thủ công."""
    payload = DocumentPayload(
        so_van_ban="999/ABC-XYZ",
        loai_van_ban="Công văn",
        co_quan_ban_hanh="Công ty TNHH Thương mại ABC",
        nguoi_ky="Nguyễn Văn A",
        ngay_van_ban="2026-08-08",
        trich_yeu="V/v đề nghị xúc tiến thương mại, quảng bá sản phẩm nông sản",
    )
    harness = Harness()
    resp = harness.route(payload, pdf_text="", pdf_name="")
    assert resp.warning and "API_KEY" in resp.warning
    assert resp.needs_human_review is True
