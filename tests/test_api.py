"""Integration test API (FastAPI TestClient) — không cần server riêng."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SOURCE_DIR = Path(__file__).resolve().parent.parent / "source"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["model"] == "deepseek-reasoner"  # core model mặc định
    assert data["llm_available"] is False  # chưa có key trong môi trường test


def test_rules_listing():
    r = client.get("/rules")
    assert r.status_code == 200
    data = r.json()
    assert data["version"] == "0.1.0"
    assert data["so_luong"]["ngoai_le"] >= 10
    assert data["so_luong"]["linh_vuc"] >= 9


def test_classify_json_rule_path():
    payload = {
        "so_van_ban": "8682/SNNMT-CNTY",
        "loai_van_ban": "Công văn",
        "co_quan_ban_hanh": "Chi cục Chăn nuôi và Thú y",
        "nguoi_ky": "Nguyễn Văn A",
        "ngay_van_ban": "2026-08-05",
        "trich_yeu": "V/v tăng cường kiểm tra, giám sát dịch bệnh động vật, vệ sinh thú y",
    }
    r = client.post("/classify/json", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["method"] == "rule_engine"
    assert any("Đoàn Ngọc Có" in rec["ten"] for rec in data["recipients"])


def test_classify_multipart_with_pdf():
    # Dùng PDF CNTY để payload và nội dung PDF cùng tín hiệu (Chăn nuôi & Thú y)
    cnty_pdfs = sorted(SOURCE_DIR.glob("*CNTY*.pdf"))
    pdf = cnty_pdfs[0] if cnty_pdfs else sorted(SOURCE_DIR.glob("*.pdf"))[0]
    payload = {
        "so_van_ban": "8682/SNNMT-CNTY",
        "loai_van_ban": "Công văn",
        "co_quan_ban_hanh": "Chi cục Chăn nuôi và Thú y",
        "nguoi_ky": "",
        "ngay_van_ban": "2026-08-05",
        "trich_yeu": "V/v tăng cường kiểm tra, giám sát dịch bệnh động vật, vệ sinh thú y và chất cấm trong chăn nuôi",
    }
    with open(pdf, "rb") as f:
        r = client.post(
            "/classify",
            data=payload,
            files={"pdf": (pdf.name, f, "application/pdf")},
        )
    assert r.status_code == 200
    data = r.json()
    assert any("Đoàn Ngọc Có" in rec["ten"] for rec in data["recipients"])
    assert data["confidence"] >= 0.8


def test_audit_entries_exist():
    # đảm bảo có ít nhất 1 bản ghi audit (tự tạo, không phụ thuộc DB cũ)
    client.post(
        "/classify/json",
        json={
            "so_van_ban": "AUDIT-TEST",
            "loai_van_ban": "Công văn",
            "co_quan_ban_hanh": "Cơ quan kiểm tra",
            "nguoi_ky": "",
            "ngay_van_ban": "2026-08-08",
            "trich_yeu": "V/v kiểm tra audit log",
        },
    )
    r = client.get("/audit")
    assert r.status_code == 200
    entries = r.json()
    assert isinstance(entries, list)
    assert len(entries) >= 1
    assert entries[0]["job_id"]
