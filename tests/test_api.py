"""Smoke test cho API /classify (dùng text override, không cần PDF thật)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from app.main import app

        # dùng context manager để chạy lifespan (khởi tạo harness)
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_classify_thuy_loi(self):
        r = self.client.post(
            "/classify",
            data={"text": "CÔNG VĂN\nV/v: xây dựng công trình thủy lợi\n"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("V.9", body["matched_rules"])
        self.assertIn("PGĐ Vũ Ngọc An", body["don_vi_xu_ly_chinh"])

    def test_classify_no_input_400(self):
        r = self.client.post("/classify", data={})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
