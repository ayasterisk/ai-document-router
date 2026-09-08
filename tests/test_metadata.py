"""Unit test cho MetadataExtractor (trích metadata + hạn từ nội dung văn bản)."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.extract.metadata import MetadataExtractor


class TestMetadataExtractor(unittest.TestCase):
    def test_so_hieu(self):
        self.assertEqual(
            MetadataExtractor.extract_so_hieu("Số: 123/SNNMT-TS\nCÔNG VĂN"),
            "123/SNNMT-TS",
        )

    def test_loai(self):
        self.assertEqual(
            MetadataExtractor.extract_loai("CÔNG VĂN\nSố: 1/ABC"), "Công văn"
        )

    def test_ngay_van_ban(self):
        self.assertEqual(
            MetadataExtractor.extract_ngay_van_ban("..., ngày 15 tháng 8 năm 2026"),
            date(2026, 8, 15),
        )

    def test_han_thuc_hien_ngay(self):
        self.assertEqual(
            MetadataExtractor.extract_han_thuc_hien(
                "Đề nghị trả lời trước ngày 20/08/2026"
            ),
            "2026-08-20",
        )

    def test_han_thuc_hien_khan(self):
        self.assertEqual(
            MetadataExtractor.extract_han_thuc_hien("CÔNG ĐIỆN HỎA TỐC"),
            None,
        )

    def test_detect_khan(self):
        self.assertTrue(MetadataExtractor.detect_khan("Văn bản KHẨN"))

    def test_trich_yeu(self):
        self.assertIn(
            "thu hồi đất",
            MetadataExtractor.extract_trich_yeu("V/v: thông báo thu hồi đất do nợ thuế")
            or "",
        )

    def test_extract_tong_hop(self):
        text = (
            "CÔNG VĂN\nSố: 55/SNNMT-TS\n"
            "V/v: báo cáo nuôi trồng thủy sản\n"
            "Trả lời trước ngày 25/08/2026"
        )
        meta = MetadataExtractor.extract(text)
        self.assertEqual(meta.so_hieu, "55/SNNMT-TS")
        self.assertEqual(meta.loai, "Công văn")
        self.assertEqual(meta.han_thuc_hien, "2026-08-25")


if __name__ == "__main__":
    unittest.main(verbosity=2)
