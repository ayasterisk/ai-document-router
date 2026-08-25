"""Unit test cho rule engine + harness (fallback T2->T1->T0)."""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

# cho phép import `app.*` khi chạy từ thư mục gốc repo
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.harness import Harness, MockInferenceClient  # noqa: E402
from app.rules.engine import Document, RuleEngine, norm, strip_accents  # noqa: E402

RULES_PATH = ROOT / "app" / "rules" / "rules.yaml"


def make_doc(**kwargs) -> Document:
    defaults = dict(
        so_hieu="",
        loai="Công văn",
        co_quan_ban_hanh="",
        nguoi_ky="",
        ngay_van_ban=date(2026, 8, 1),
        trich_yeu="",
        han_xu_ly=None,
        noi_dung="",
    )
    defaults.update(kwargs)
    return Document(**defaults)


class TestNormalization(unittest.TestCase):
    def test_strip_accents(self):
        self.assertEqual(norm("Thủy Lợi"), "thuy loi")
        self.assertEqual(norm("Đất đai"), "dat dai")
        self.assertEqual(strip_accents("ĐCKS"), "dcks")


class TestSourceDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(RULES_PATH)

    def test_cap_tren(self):
        self.assertEqual(self.engine.detect_source(make_doc(co_quan_ban_hanh="UBND tỉnh Gia Lai")), "cap_tren")

    def test_so_nganh(self):
        self.assertEqual(self.engine.detect_source(make_doc(co_quan_ban_hanh="Sở Tài chính")), "so_nganh")

    def test_cuc_thue_la_so_nganh(self):
        self.assertEqual(self.engine.detect_source(make_doc(co_quan_ban_hanh="Cục Thuế tỉnh Gia Lai")), "so_nganh")

    def test_khac(self):
        self.assertEqual(self.engine.detect_source(make_doc(co_quan_ban_hanh="Công ty TNHH ABC")), "khac")

    def test_khong_ro(self):
        self.assertIsNone(self.engine.detect_source(make_doc(co_quan_ban_hanh="Xyz")))


class TestEngineRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(RULES_PATH)

    def test_ky_hieu_uu_tien_cao_nhat(self):
        doc = make_doc(so_hieu="123/SNNMT-TS", trich_yeu="báo cáo nuôi trồng thủy sản")
        res = self.engine.run(doc)
        self.assertIn("IV", res.matched_rules)
        self.assertEqual(res.assignments[0]["target"], "Chi cục Thủy sản")

    def test_ngoai_le_thue_thu_hoi_dat(self):
        doc = make_doc(
            co_quan_ban_hanh="Cục Thuế tỉnh Gia Lai",
            trich_yeu="Thông báo thu hồi đất do nợ thuế",
        )
        res = self.engine.run(doc)
        self.assertIn("V.3", res.matched_rules)
        self.assertEqual(res.assignments[0]["target"], "Chi cục Quản lý đất đai")

    def test_thuy_loi_binh_thuong(self):
        doc = make_doc(trich_yeu="xây dựng công trình thủy lợi", han_xu_ly=None)
        res = self.engine.run(doc)
        self.assertIn("V.9", res.matched_rules)
        self.assertEqual(res.assignments[0]["target"], "PGĐ Vũ Ngọc An")

    def test_thuy_loi_khan_dung_muc_VI(self):
        today = date(2026, 8, 1)
        doc = make_doc(
            trich_yeu="phòng chống lụt bão công trình thủy lợi",
            han_xu_ly=today + timedelta(days=1),
        )
        res = self.engine.run(doc, today=today)
        self.assertIn("VI.1", res.matched_rules)
        self.assertEqual(res.assignments[0]["target"], "PGĐ Vũ Ngọc An")
        self.assertEqual(res.assignments[1]["target"], "Chi cục Thủy lợi")

    def test_giay_moi(self):
        doc = make_doc(loai="Giấy mời", trich_yeu="kính mời dự họp")
        res = self.engine.run(doc)
        self.assertIn("II.4", res.matched_rules)

    def test_cap_tren_trong_trot_ve_pgd(self):
        doc = make_doc(
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="chương trình trồng trọt vụ đông xuân",
        )
        res = self.engine.run(doc)
        self.assertIn("II.cap_tren.pgd", res.matched_rules)
        targets = [a["target"] for a in res.assignments]
        self.assertIn("PGĐ Nguyễn Thị Tố Trân", targets)
        self.assertIn("Giám đốc Cao Thanh Thương", targets)  # theo dõi

    def test_ubnd_chap_thuan_chu_truong_dau_tu(self):
        doc = make_doc(
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="Quyết định chấp thuận chủ trương đầu tư dự án",
        )
        res = self.engine.run(doc)
        self.assertIn("V.12", res.matched_rules)
        targets = [a["target"] for a in res.assignments]
        self.assertIn("Trưởng phòng KH-TC Châu Thái Quy", targets)  # nhóm thẩm định
        self.assertIn("Lãnh đạo Sở", targets)  # phối hợp xử lý

    def test_ubnd_chap_thuan_chu_truong_dau_tu_chan_nuoi(self):
        doc = make_doc(
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="Quyết định chấp thuận chủ trương đầu tư trang trại chăn nuôi",
        )
        res = self.engine.run(doc)
        self.assertIn("V.11", res.matched_rules)
        targets = [a["target"] for a in res.assignments]
        self.assertIn("Chi cục Chăn nuôi và Thú y", targets)

    def test_ubnd_tham_dinh_dtm(self):
        doc = make_doc(
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="Quyết định thẩm định báo cáo đánh giá tác động môi trường",
        )
        res = self.engine.run(doc)
        self.assertIn("V.13", res.matched_rules)
        targets = [a["target"] for a in res.assignments]
        self.assertIn("PGĐ Hà Thị Thanh Hương", targets)
        self.assertIn("Chi cục Bảo vệ môi trường", targets)
        self.assertIn("Giám đốc Cao Thanh Thương", targets)  # theo dõi

    def test_khong_khop_flag_review(self):
        doc = make_doc(co_quan_ban_hanh="Xyz", trich_yeu="nội dung không rõ ràng")
        res = self.engine.run(doc)
        self.assertTrue(res.needs_review)
        self.assertEqual(res.assignments, [])

    def test_chuan_hoa_ten(self):
        self.assertEqual(self.engine.normalize_person("Bảo Chi"), "Trần Thị Bảo Chi")
        self.assertEqual(self.engine.normalize_person("PGĐ An"), "PGĐ Vũ Ngọc An")


class TestHarnessFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(RULES_PATH)

    def test_happy_path_t0(self):
        h = Harness(self.engine, MockInferenceClient(), mode="auto")
        doc = make_doc(trich_yeu="xây dựng công trình thủy lợi")
        res = h.run(doc)
        self.assertEqual(res.tier, "T0")
        self.assertFalse(res.degraded)
        self.assertIn("V.9", res.matched_rules)

    def test_fallback_t1_khi_khong_khop(self):
        client = MockInferenceClient(supports_tool_calling=False)
        h = Harness(self.engine, client, mode="auto")
        doc = make_doc(co_quan_ban_hanh="Xyz", trich_yeu="nội dung không rõ ràng")
        res = h.run(doc)
        # mock model trả kết quả -> không về T0 mà dùng T1
        self.assertEqual(res.tier, "T1")
        self.assertFalse(res.needs_review)

    def test_mode_off_t0_degraded(self):
        h = Harness(self.engine, MockInferenceClient(), mode="off")
        doc = make_doc(co_quan_ban_hanh="Xyz", trich_yeu="nội dung không rõ ràng")
        res = h.run(doc)
        self.assertEqual(res.tier, "T0")
        self.assertTrue(res.degraded)
        self.assertTrue(res.needs_review)


if __name__ == "__main__":
    unittest.main(verbosity=2)
