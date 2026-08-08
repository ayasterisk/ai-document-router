"""Giả lập + TRACING chi tiết cho server AI Document Router.

Chạy 7 kịch bản đại diện qua pipeline thật (verify -> rule engine -> decision
-> LLM/audit) và ghi toàn bộ trace ra:
  - console
  - simulation_trace.txt  (bản text dễ đọc)
  - simulation_trace.json (bản đầy đủ)

Kịch bản 7 (rule không khớp) dùng MOCK deepseek-reasoner vì máy local chưa có
DEEPSEEK_API_KEY — nội dung mock thể hiện đúng luồng gọi LLM thật.

Chạy:  .venv\\Scripts\\python scripts\\simulate.py
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app.models.schema import DocumentPayload
from app.orchestrator.harness import Harness
from app.pdf.extractor import extract_text_from_file


class MockDeepSeekReasoner:
    """Giả lập phản hồi deepseek-reasoner (JSON + reasoning_content)."""

    available = True

    def __init__(self, llm_json: dict, reasoning: str):
        self.llm_json = llm_json
        self._reasoning = reasoning
        self.model = "deepseek-reasoner (MOCK)"

    def chat(self, system, user, response_format=None, max_tokens=None):
        time.sleep(0.05)  # mô phỏng độ trễ API
        return json.dumps(self.llm_json, ensure_ascii=False), self._reasoning, None


def make_payload(**kw) -> DocumentPayload:
    defaults = dict(
        so_van_ban="", loai_van_ban="Công văn", co_quan_ban_hanh="",
        nguoi_ky="", ngay_van_ban="2026-08-08", trich_yeu="",
    )
    defaults.update(kw)
    return DocumentPayload(**defaults)


# --------------------------------------------------------------------------
# Định nghĩa kịch bản
# --------------------------------------------------------------------------
SCENARIOS = [
    {
        "id": "S1",
        "name": "Khiếu nại của công dân -> Ngoại lệ IV.2",
        "payload": make_payload(
            co_quan_ban_hanh="Công dân Nguyễn Văn A",
            trich_yeu="Đơn đề nghị giải quyết khiếu nại về đất đai",
        ),
    },
    {
        "id": "S2",
        "name": "Giấy mời họp -> Mục II.4",
        "payload": make_payload(
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="Giấy mời tham dự cuộc họp triển khai nhiệm vụ 6 tháng cuối năm",
        ),
    },
    {
        "id": "S3",
        "name": "Giao Sở chủ trì -> Giám đốc bút phê trước (Mục I/II.1)",
        "payload": make_payload(
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="V/v giao Sở Nông nghiệp và Môi trường chủ trì xử lý, phối hợp với các sở ngành liên quan",
        ),
    },
    {
        "id": "S4",
        "name": "Công văn khẩn phòng chống lụt bão -> Mục V (song song)",
        "payload": make_payload(
            loai_van_ban="Công văn khẩn",
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="V/v ứng phó mưa lũ, phòng chống lụt bão trên địa bàn tỉnh",
        ),
    },
    {
        "id": "S5",
        "name": "Giao đất, cho thuê đất -> Mục III (Chi cục QLĐĐ) + mã ký hiệu QLDD",
        "payload": make_payload(
            so_van_ban="8708/SNNMT-QLDD",
            co_quan_ban_hanh="UBND tỉnh Gia Lai",
            trich_yeu="V/v giao đất, cho thuê đất đối với các thửa đất nhỏ hẹp, nằm xen kẹt",
        ),
    },
    {
        "id": "S6",
        "name": "PDF THẬT source/8682_SNNMT-CNTY -> Mục III (Chăn nuôi & Thú y)",
        "payload": make_payload(
            so_van_ban="8682/SNNMT-CNTY",
            co_quan_ban_hanh="Sở Nông nghiệp và Môi trường tỉnh Gia Lai",
            trich_yeu="V/v tăng cường quản lý hoạt động nhập khẩu, buôn bán, sử dụng thuốc thú y trên địa bàn tỉnh",
        ),
        "pdf": ROOT / "source" / "8682_SNNMT-CNTY_04082026-signed.pdf",
    },
]

SCENARIOS.append(
    {
        "id": "S7",
        "name": "Nội dung không khớp rule cứng -> deepseek-reasoner suy luận",
        "payload": make_payload(
            co_quan_ban_hanh="Công ty TNHH Thương mại ABC",
            trich_yeu="V/v đề nghị hỗ trợ xúc tiến thương mại, quảng bá sản phẩm nông sản",
        ),
        "mock_llm": {
            "recipients": [
                {"ten": "PGĐ Nguyễn Thị Tố Trân", "vai_tro": "xử lý chính", "muc_uu_tien": 1},
                {"ten": "Chi cục Trồng trọt và BVTV", "vai_tro": "xử lý chính", "muc_uu_tien": 1},
            ],
            "confidence": 0.82,
            "matched_rules": [
                {"rule_id": "llm", "name": "Suy luận ngữ nghĩa", "reason": "Nội dung nông sản -> lĩnh vực trồng trọt"}
            ],
            "reasoning": "Văn bản xúc tiến thương mại sản phẩm nông sản thuộc lĩnh vực trồng trọt/khuyến nông, "
                         "theo Mục III thuộc PGĐ Nguyễn Thị Tố Trân (Chi cục Trồng trọt và BVTV).",
            "needs_human_review": False,
        },
        "mock_reasoning_content": (
            "Tôi xác định lĩnh vực: 'xúc tiến thương mại sản phẩm nông sản' không khớp keyword "
            "rule cứng. Đối chiếu rulebase Mục III, nội dung nông nghiệp tổng hợp thuộc PGĐ "
            "Nguyễn Thị Tố Trân (trồng trọt, khuyến nông, chất lượng nông sản). Quy tắc nguồn "
            "II.3 (doanh nghiệp): đơn vị tham mưu xử lý chính. Trả JSON..."
        ),
    }
)


def format_trace(events: list) -> str:
    lines = []
    for i, ev in enumerate(events, 1):
        lines.append(f"  [{i:02d}] {ev['event']}:")
        for k, v in ev.items():
            if k == "event":
                continue
            lines.append(f"        {k}: {json.dumps(v, ensure_ascii=False)[:400]}")
    return "\n".join(lines)



def main() -> int:
    all_records = []
    text_out = []
    header = "=" * 78
    text_out.append(header)
    text_out.append("AI DOCUMENT ROUTER — GIẢ LẬP & TRACING (core: deepseek-reasoner)")
    text_out.append("Thời điểm: " + time.strftime("%Y-%m-%d %H:%M:%S"))
    text_out.append(header)

    for sc in SCENARIOS:
        t0 = time.time()
        payload = sc["payload"]

        pdf_text, pdf_name = "", ""
        if sc.get("pdf") and sc["pdf"].exists():
            pdf_text, _engine_used, _ocr = extract_text_from_file(str(sc["pdf"]))
            pdf_name = sc["pdf"].name

        harness = Harness()
        if sc.get("mock_llm"):
            harness = Harness(llm=MockDeepSeekReasoner(sc["mock_llm"], sc["mock_reasoning_content"]))

        resp = harness.route(payload, pdf_text=pdf_text, pdf_name=pdf_name)
        elapsed = time.time() - t0

        record = {
            "id": sc["id"],
            "name": sc["name"],
            "payload": payload.model_dump(),
            "pdf_name": pdf_name,
            "response": resp.model_dump(),
            "trace": harness.trace,
            "elapsed_ms": round(elapsed * 1000, 1),
        }
        all_records.append(record)

        text_out.append("")
        text_out.append("-" * 78)
        text_out.append(f"[{sc['id']}] {sc['name']}  ({record['elapsed_ms']} ms)")
        text_out.append("-" * 78)
        text_out.append("  TRACE (pipeline):")
        text_out.append(format_trace([e for e in harness.trace if e["event"] != "rule_engine"]))
        # in riêng trace rule engine (nằm trong event rule_engine)
        for ev in harness.trace:
            if ev.get("event") == "rule_engine" and ev.get("engine_trace"):
                text_out.append("  TRACE (rule engine — từng bước ưu tiên):")
                for j, st in enumerate(ev["engine_trace"], 1):
                    st_lines = []
                    for k, v in st.items():
                        if isinstance(v, (list, dict)):
                            v = json.dumps(v, ensure_ascii=False)[:300]
                        st_lines.append(f"{k}={v}")
                    text_out.append(f"    - [{j}] {st['event']}: " + ", ".join(st_lines))
        text_out.append("")
        text_out.append(f"  KẾT QUẢ: method={resp.method} | confidence={resp.confidence} | "
                        f"needs_human_review={resp.needs_human_review}")
        if resp.warning:
            text_out.append(f"  WARNING: {resp.warning}")
        text_out.append("  RECIPIENTS:")
        for r in resp.recipients:
            text_out.append(f"    - {r.ten}  [{r.vai_tro}]  (nguon: {r.nguon})")
        text_out.append("  MATCHED RULES:")
        for mr in resp.matched_rules:
            text_out.append(f"    [{mr.rule_id}] {mr.name} — {mr.reason} (conf={mr.confidence})")
        if resp.reasoning:
            text_out.append(f"  REASONING: {resp.reasoning[:300]}")
        if resp.llm_reasoning_preview:
            text_out.append(f"  LLM reasoning_content (preview): {resp.llm_reasoning_preview[:200]}")

    # Ghi file
    (ROOT / "simulation_trace.txt").write_text("\n".join(text_out), encoding="utf-8")
    (ROOT / "simulation_trace.json").write_text(
        json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # In ra console
    print("\n".join(text_out))
    print()
    print(f"Đã ghi: simulation_trace.txt và simulation_trace.json ({len(all_records)} kịch bản)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
