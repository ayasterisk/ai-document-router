"""Demo: chạy pipeline định tuyến trên vài văn bản mẫu, in kết quả 4 trường."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.orchestrator.harness import Harness, MockInferenceClient  # noqa: E402
from app.rules.engine import RuleEngine  # noqa: E402

RULES = ROOT / "app" / "rules" / "rules.yaml"

SAMPLES = [
    ("Thuế - thu hồi đất", "CỤC THUẾ TỈNH GIA LAI\nCÔNG VĂN\nV/v: Thông báo thu hồi đất do nợ thuế"),
    ("Thủy lợi - bình thường", "SỞ NN&MT\nCÔNG VĂN\nV/v: xây dựng công trình thủy lợi"),
    ("Khẩn - hỏa tốc thủy lợi", "CÔNG ĐIỆN HỎA TỐC\nV/v: phòng chống lụt bão công trình thủy lợi"),
    ("Ký hiệu văn bản (SNNMT-TS)", "SỞ NN&MT\nCÔNG VĂN\nSố: 123/SNNMT-TS\nV/v: báo cáo nuôi trồng thủy sản"),
    ("UBND tỉnh - thẩm định ĐTM", "UBND TỈNH GIA LAI\nQUYẾT ĐỊNH\nV/v: thẩm định báo cáo đánh giá tác động môi trường"),
    ("UBND tỉnh - chấp thuận chủ trương đầu tư (chăn nuôi)", "UBND TỈNH GIA LAI\nQUYẾT ĐỊNH\nV/v: chấp thuận chủ trương đầu tư trang trại chăn nuôi"),
]


def main() -> None:
    engine = RuleEngine(RULES)
    harness = Harness(engine, MockInferenceClient(), mode="auto")
    for name, text in SAMPLES:
        r = harness.run(text)
        print("=" * 72)
        print("TRƯỜNG HỢP:", name)
        print(
            json.dumps(
                {
                    "don_vi_xu_ly_chinh": r.don_vi_xu_ly_chinh,
                    "phoi_hop_xu_ly": r.phoi_hop_xu_ly,
                    "lanh_dao_theo_doi": r.lanh_dao_theo_doi,
                    "han_thuc_hien": r.han_thuc_hien,
                    "matched_rules": r.matched_rules,
                    "tier": r.tier,
                    "confidence": r.confidence,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
