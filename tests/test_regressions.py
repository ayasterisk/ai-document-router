"""Counterexamples from the SoNNMT review, including negative evidence."""

import json
import unittest
from datetime import date
from pathlib import Path

from app.extract.metadata import MetadataExtractor
from app.orchestrator.harness import Harness, InferenceClient
from app.rules.engine import Document, RuleEngine, _contains, norm

TODAY = date(2026, 9, 8)


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RuleEngine("app/rules/rules.yaml")

    def run_doc(self, subject, source="UBND tỉnh Gia Lai", **kwargs):
        return self.engine.run(
            Document(trich_yeu=subject, co_quan_ban_hanh=source, **kwargs), TODAY
        )

    def test_v8b_and_v8(self):
        self.assertEqual(
            self.run_doc(
                "Báo cáo kết quả thẩm định chủ trương đầu tư dự án",
                "Sở Tài chính",
                loai="Báo cáo",
            ).matched_rules,
            ["V.8b"],
        )
        self.assertEqual(
            self.run_doc(
                "Lấy ý kiến thẩm định dự án", "Sở Tài chính", loai="Công văn"
            ).matched_rules,
            ["V.8"],
        )
        self.assertNotEqual(
            self.run_doc(
                "Thẩm định chủ trương đầu tư", "Sở Tài chính", loai="Công văn"
            ).matched_rules,
            ["V.8b"],
        )

    def test_harbor_urgent(self):
        r = self.run_doc("Khu neo đậu tránh trú bão cho tàu cá", khan=True)
        self.assertEqual(r.matched_rules, ["VI.4"])
        self.assertIn("BQL cảng cá", r.don_vi_xu_ly_chinh)

    def test_phrase_boundaries(self):
        self.assertFalse(_contains(norm("công nghệ cao"), "nghề cá"))
        self.assertTrue(_contains(norm("công trình\n thủy lợi"), "công trình thủy lợi"))
        r = self.run_doc("nông nghiệp công nghệ cao")
        self.assertNotIn("Phó giám đốc (Trần Quốc Khánh)", r.don_vi_xu_ly_chinh)

    def test_domain_and_units(self):
        self.assertIn(
            "Phó giám đốc (Trần Quốc Khánh)",
            self.run_doc("Ứng phó biến đổi khí hậu").don_vi_xu_ly_chinh,
        )
        self.assertIn(
            "Trung tâm Quan trắc tài nguyên và môi trường",
            self.run_doc("Quan trắc").don_vi_xu_ly_chinh,
        )
        self.assertIn(
            "Trung tâm Giống Nông nghiệp",
            self.run_doc("Giống nông nghiệp").don_vi_xu_ly_chinh,
        )

    def test_composite(self):
        r = self.run_doc(
            "Trồng trọt, bảo vệ thực vật, giống cây trồng; chăn nuôi, thú y"
        )
        self.assertEqual(r.matched_rules, ["II.cap_tren.tong_hop"])
        self.assertEqual(r.don_vi_xu_ly_chinh, ["Giám đốc (Cao Thanh Thương)"])

    def test_finance_and_personnel(self):
        for text, rule, unit in [
            ("Ngân sách, dự toán", "II.cap_tren.khtc", "Phòng Kế hoạch - Tài chính"),
            ("Bổ nhiệm cán bộ", "II.cap_tren.tccb", "Phòng Tổ chức cán bộ"),
        ]:
            r = self.run_doc(text)
            self.assertEqual(r.matched_rules, [rule])
            self.assertEqual(r.don_vi_xu_ly_chinh, [unit])
            self.assertEqual(r.phoi_hop_xu_ly, ["Giám đốc (Cao Thanh Thương)"])

    def test_v6_requires_real_context(self):
        r = self.run_doc(
            "Điều tra vụ án khai thác khoáng sản trái phép", "Công an tỉnh Gia Lai"
        )
        self.assertNotIn("V.6", r.matched_rules)

    def test_unverified_mapping(self):
        r = self.run_doc("Trả lời Công văn số 123/SNNMT-VPĐK")
        self.assertEqual(r.matched_rules, ["IV"])
        self.assertTrue(r.needs_review)
        self.assertEqual(r.don_vi_xu_ly_chinh, [])

    def test_reply_relation(self):
        r = self.run_doc(
            "Trả lời Công văn số 12/SNNMT-TS; tàu cá", noi_dung="Căn cứ 55/SNNMT-TCCB."
        )
        self.assertEqual(r.extracted["ky_hieu"], "SNNMT-TS")
        self.assertNotEqual(
            self.run_doc(
                "Báo cáo tàu cá", noi_dung="Căn cứ 12/SNNMT-TS."
            ).matched_rules,
            ["IV"],
        )
        self.assertNotEqual(
            self.run_doc("Báo cáo tàu cá", so_hieu="12/SNNMT-TS").matched_rules, ["IV"]
        )

    def test_reviewed_samples_351_and_4326(self):
        cases = json.loads(
            Path("output/sonnmt_ocr_audit/verified_metadata.json").read_text(
                encoding="utf-8"
            )
        )
        for num, expected in [(5, "II.cap_tren.tong_hop"), (7, "IV")]:
            m = next(m for m in cases if m["id"] == num)
            r = self.run_doc(
                m["trich_yeu"],
                m["co_quan_ban_hanh"],
                loai=m["loai"],
                noi_dung=m["relevant_text"],
            )
            self.assertEqual(r.matched_rules, [expected])

    def test_urgency_and_dates(self):
        m = MetadataExtractor.extract(
            "BÁO CÁO\nCông tác phòng chống dịch bệnh khẩn cấp năm 2025"
        )
        self.assertFalse(m.khan)
        self.assertIsNone(m.han_thuc_hien)
        self.assertEqual(
            MetadataExtractor.extract("CÔNG ĐIỆN HỎA TỐC").do_khan, "hoa_toc"
        )
        m = MetadataExtractor.extract(
            "Đề nghị hoàn thành trước ngày 10 tháng 9 năm 2026"
        )
        self.assertIsNone(m.ngay_van_ban)
        self.assertEqual(m.han_thuc_hien, "2026-09-10")
        r = self.run_doc("thủy lợi", han_thuc_hien="2020-01-01")
        self.assertEqual(r.matched_rules, ["V.9"])
        self.assertIn("overdue_deadline", r.review_reasons)

    def test_ambiguous_and_relative_deadline(self):
        m = MetadataExtractor.extract(
            "Hoàn thành trước ngày 10/09/2026; trả lời chậm nhất ngày 12/09/2026"
        )
        self.assertIsNone(m.han_thuc_hien)
        self.assertIn("multiple_deadlines", m.warnings)
        m = MetadataExtractor.extract(
            "Trả lời trong thời hạn 3 ngày kể từ ngày nhận", TODAY
        )
        self.assertEqual(m.han_thuc_hien, "2026-09-11")

    def test_header_not_recipient(self):
        m = MetadataExtractor.extract(
            "V/v triển khai nhiệm vụ\nKính gửi: Sở Nông nghiệp và Môi trường"
        )
        self.assertEqual(m.trich_yeu, "triển khai nhiệm vụ")
        self.assertIsNone(m.co_quan_ban_hanh)

    def test_assignment_excludes_other_department(self):
        text = "KẾ HOẠCH\n1. Sở Tài chính:\nChuẩn bị giấy mời.\n2. Sở Nông nghiệp và Môi trường:\nQuan trắc.\n3. Sở Nội vụ:\nBổ nhiệm cán bộ."
        r = self.run_doc("Triển khai nhiệm vụ", noi_dung=text)
        self.assertFalse(r.extracted["giay_moi"])
        self.assertEqual(r.extracted["linh_vuc"], "bảo vệ môi trường")


class Client(InferenceClient):
    supports_tool_calling = True

    def __init__(self, answers):
        self.answers = iter(answers)
        self.messages = []

    def generate(self, messages, tools=None):
        self.messages.append(list(messages))
        return next(self.answers)


class HarnessValidationTests(unittest.TestCase):
    def setUp(self):
        self.engine = RuleEngine("app/rules/rules.yaml")

    def test_no_implicit_mock(self):
        r = Harness(self.engine).run("nội dung không rõ")
        self.assertTrue(r.needs_review)
        self.assertEqual(r.don_vi_xu_ly_chinh, [])

    def test_invalid_json_and_empty_result_fall_back(self):
        for output in ["{}", "[]", "null", "bad", json.dumps({"confidence": "oops"})]:
            c = Client(
                [
                    {
                        "tool_calls": [
                            {
                                "id": "x",
                                "function": {"name": "apply_rules", "arguments": "bad"},
                            }
                        ]
                    },
                    {"content": output},
                    {"content": output},
                ]
            )
            r = Harness(self.engine, c).run("nội dung không rõ")
            self.assertEqual(r.tier, "T0")
            self.assertTrue(r.needs_review)

    def test_tool_order_and_grounded_deadline(self):
        final = {
            "don_vi_xu_ly_chinh": ["Chi cục Thủy lợi"],
            "confidence": 0.9,
            "reason": "Gợi ý",
            "han_thuc_hien": "2030-01-01",
            "needs_review": False,
        }
        c = Client(
            [
                {
                    "tool_calls": [
                        {
                            "id": "x",
                            "type": "function",
                            "function": {"name": "apply_rules", "arguments": "{}"},
                        }
                    ]
                },
                {"content": json.dumps(final)},
            ]
        )
        r = Harness(self.engine, c).run("nội dung không rõ", TODAY)
        self.assertEqual(
            [m["role"] for m in c.messages[1]], ["system", "user", "assistant", "tool"]
        )
        self.assertTrue(r.needs_review)
        self.assertIsNone(r.han_thuc_hien)
        self.assertTrue(r.extracted_metadata)

    def test_unknown_recipient_rejected(self):
        content = json.dumps(
            {"don_vi_xu_ly_chinh": ["invented"], "confidence": 1, "reason": "x"}
        )
        self.assertIsNone(Harness(self.engine)._parse_final(content, "T2"))


if __name__ == "__main__":
    unittest.main()
