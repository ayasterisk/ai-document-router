"""Unit test cho rule engine (output 4 trường) + harness (fallback T2->T1->T0)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

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
        noi_dung="",
        han_thuc_hien=None,
        khan=False,
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
        self.assertEqual(res.don_vi_xu_ly_chinh, ["Chi cục Thủy sản"])

    def test_ngoai_le_thue_thu_hoi_dat(self):
        doc = make_doc(co_quan_ban_hanh="Cục Thuế tỉnh Gia Lai", trich_yeu="thu hồi đất do nợ thuế")
        res = self.engine.run(doc)
        self.assertIn("V.3", res.matched_rules)
        self.assertEqual(res.don_vi_xu_ly_chinh, ["Chi cục Quản lý đất đai"])

    def test_thuy_loi_binh_thuong(self):
        doc = make_doc(trich_yeu="xây dựng công trình thủy lợi")
        res = self.engine.run(doc)
        self.assertIn("V.9", res.matched_rules)
        self.assertEqual(res.don_vi_xu_ly_chinh, ["PGĐ Vũ Ngọc An"])

    def test_thuy_loi_khan_dung_muc_VI(self):
        doc = make_doc(trich_yeu="phòng chống lụt bão công trình thủy lợi", khan=True)
        res = self.engine.run(doc)
        self.assertIn("VI.1", res.matched_rules)
        self.assertEqual(res.don_vi_xu_ly_chinh, ["PGĐ Vũ Ngọc An", "Chi cục Thủy lợi"])

    def test_giay_moi(self):
        doc = make_doc(loai="Giấy mời", trich_yeu="kính mời dự họp")
        res = self.engine.run(doc)
        self.assertIn("II.4", res.matched_rules)

    def test_cap_tren_trong_trot_ve_pgd(self):
        doc = make_doc(co_quan_ban_hanh="UBND tỉnh Gia Lai", trich_yeu="chương trình trồng trọt vụ đông xuân")
        res = self.engine.run(doc)
        self.assertIn("II.cap_tren.pgd", res.matched_rules)
        self.assertIn("PGĐ Nguyễn Thị Tố Trân", res.don_vi_xu_ly_chinh)
        self.assertIn("Giám đốc Cao Thanh Thương", res.lanh_dao_theo_doi)

    def test_ubnd_chap_thuan_chu_truong_dau_tu(self):
        doc = make_doc(co_quan_ban_hanh="UBND tỉnh Gia Lai", trich_yeu="Quyết định chấp thuận chủ trương đầu tư dự án")
        res = self.engine.run(doc)
        self.assertIn("V.12", res.matched_rules)
        self.assertIn("Trưởng phòng KH-TC Châu Thái Quy", res.don_vi_xu_ly_chinh)
        self.assertIn("Lãnh đạo Sở", res.phoi_hop_xu_ly)

    def test_ubnd_tham_dinh_dtm(self):
        doc = make_doc(co_quan_ban_hanh="UBND tỉnh Gia Lai", trich_yeu="Quyết định thẩm định báo cáo đánh giá tác động môi trường")
        res = self.engine.run(doc)
        self.assertIn("V.13", res.matched_rules)
        self.assertIn("PGĐ Hà Thị Thanh Hương", res.don_vi_xu_ly_chinh)
        self.assertIn("Chi cục Bảo vệ môi trường", res.don_vi_xu_ly_chinh)
        self.assertIn("Giám đốc Cao Thanh Thương", res.lanh_dao_theo_doi)

    def test_khong_khop_flag_review(self):
        doc = make_doc(co_quan_ban_hanh="Xyz", trich_yeu="nội dung không rõ ràng")
        res = self.engine.run(doc)
        self.assertTrue(res.needs_review)
        self.assertEqual(res.don_vi_xu_ly_chinh, [])

    def test_chuan_hoa_ten(self):
        self.assertEqual(self.engine.normalize_person("Bảo Chi"), "Trần Thị Bảo Chi")
        self.assertEqual(self.engine.normalize_person("PGĐ An"), "PGĐ Vũ Ngọc An")


class TestHarnessFallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(RULES_PATH)

    def test_happy_path_t0(self):
        h = Harness(self.engine, MockInferenceClient(), mode="auto")
        text = "CÔNG VĂN\nV/v: xây dựng công trình thủy lợi\n"
        res = h.run(text)
        self.assertEqual(res.tier, "T0")
        self.assertFalse(res.degraded)
        self.assertIn("V.9", res.matched_rules)

    def test_fallback_t1_khi_khong_khop(self):
        client = MockInferenceClient(supports_tool_calling=False)
        h = Harness(self.engine, client, mode="auto")
        text = "Nội dung không rõ ràng, không có từ khóa"
        res = h.run(text)
        self.assertEqual(res.tier, "T1")
        self.assertIn("Chi cục Thủy lợi", res.don_vi_xu_ly_chinh)

    def test_mode_off_t0_degraded(self):
        h = Harness(self.engine, MockInferenceClient(), mode="off")
        text = "Nội dung không rõ ràng, không có từ khóa"
        res = h.run(text)
        self.assertEqual(res.tier, "T0")
        self.assertTrue(res.degraded)
        self.assertTrue(res.needs_review)


class TestIuuRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine(RULES_PATH)

    def test_iuu_tu_so_nganh(self):
        doc = make_doc(co_quan_ban_hanh="Công an tỉnh Gia Lai", trich_yeu="báo cáo tàu cá vi phạm IUU")
        res = self.engine.run(doc)
        self.assertIn("V.14", res.matched_rules)
        self.assertIn("Chi cục Thủy sản", res.don_vi_xu_ly_chinh)
        self.assertIn("BQL cảng cá", res.don_vi_xu_ly_chinh)

    def test_iuu_xa_ven_bien(self):
        doc = make_doc(co_quan_ban_hanh="UBND xã Cát Tiến", trich_yeu="thông tin tàu cá IUU")
        res = self.engine.run(doc)
        self.assertIn("V.15", res.matched_rules)
        self.assertIn("BQL cảng cá Tam Quan", res.don_vi_xu_ly_chinh)

    def test_iuu_xa_khac(self):
        doc = make_doc(co_quan_ban_hanh="UBND xã Ia Rsai", trich_yeu="phản ánh tàu cá IUU")
        res = self.engine.run(doc)
        self.assertIn("V.16", res.matched_rules)
        self.assertEqual(res.don_vi_xu_ly_chinh, ["PGĐ Trần Quốc Khánh", "Chi cục Thủy sản"])

    def test_thuy_san_binh_thuong_song_song(self):
        doc = make_doc(trich_yeu="nuôi trồng thủy sản")
        res = self.engine.run(doc)
        self.assertIn("V.10", res.matched_rules)
        self.assertIn("VP Điều phối về BĐKH", res.don_vi_xu_ly_chinh)


if __name__ == "__main__":
    unittest.main(verbosity=2)
