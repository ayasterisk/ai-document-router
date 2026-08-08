"""Demo CLI — chạy thử định tuyến với một PDF mẫu trong source/ (không cần API key).

Cách dùng:
    python scripts/demo.py                              # dùng PDF mẫu đầu tiên
    python scripts/demo.py "path/to/van-ban.pdf"        # dùng PDF cụ thể
    python scripts/demo.py --list                       # liệt kê PDF mẫu

Nếu có DEEPSEEK_API_KEY trong .env, phần rule không match rõ sẽ được
deepseek-reasoner suy luận thêm.
"""

import argparse
import json
import sys
from pathlib import Path

# Cho phép chạy trực tiếp: python scripts\demo.py
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Console Windows mặc định cp1252 — ép UTF-8 để in tiếng Việt
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app.models.schema import DocumentPayload
from app.orchestrator.harness import Harness
from app.pdf.extractor import extract_text_from_file

SOURCE_DIR = Path(__file__).resolve().parent.parent / "source"


def build_payload_from_pdf(pdf: Path) -> DocumentPayload:
    text, _, _ = extract_text_from_file(str(pdf))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return DocumentPayload(
        so_van_ban=pdf.stem.split("-")[0].strip(),
        loai_van_ban="Công văn",
        co_quan_ban_hanh="Sở Nông nghiệp và Môi trường tỉnh Gia Lai",
        nguoi_ky="",
        ngay_van_ban="2026-08-05",
        trich_yeu=lines[2] if len(lines) > 2 else lines[0][:150],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo AI Document Router")
    parser.add_argument("pdf", nargs="?", help="Đường dẫn PDF (mặc định: PDF mẫu đầu tiên trong source/)")
    parser.add_argument("--list", action="store_true", help="Liệt kê PDF mẫu")
    parser.add_argument("--no-llm", action="store_true", help="Không gọi LLM, chỉ chạy rule engine")
    args = parser.parse_args()

    if args.list:
        for p in sorted(SOURCE_DIR.glob("*.pdf")):
            print(p.name)
        return 0

    if args.pdf:
        pdf = Path(args.pdf)
    else:
        pdfs = sorted(SOURCE_DIR.glob("*.pdf"))
        if not pdfs:
            print("Không tìm thấy PDF trong source/ — hãy truyền đường dẫn PDF cụ thể.")
            return 1
        pdf = pdfs[0]

    print(f"PDF: {pdf.name}")
    text, engine_used, need_ocr = extract_text_from_file(str(pdf))
    print(f"PDF extract: engine={engine_used}, chars={len(text)}, need_ocr={need_ocr}")
    print("-" * 70)

    payload = build_payload_from_pdf(pdf)
    print("PAYLOAD (6 trường):")
    print(json.dumps(payload.model_dump(), ensure_ascii=False, indent=2))
    print("-" * 70)

    harness = Harness()
    resp = harness.route(
        payload,
        pdf_text=text,
        pdf_name=pdf.name,
        allow_llm=None if not args.no_llm else False,
    )
    print(f"job_id: {resp.job_id}")
    print(f"method: {resp.method} | confidence: {resp.confidence} | needs_human_review: {resp.needs_human_review}")
    if resp.warning:
        print(f"warning: {resp.warning}")
    print("RECIPIENTS:")
    for r in resp.recipients:
        print(f"  - {r.ten}  [{r.vai_tro}]  (nguon: {r.nguon})")
    print("MATCHED RULES:")
    for mr in resp.matched_rules:
        print(f"  [{mr.rule_id}] {mr.name} — {mr.reason} (conf={mr.confidence})")
    print("REASONING:", (resp.reasoning or "")[:400])
    if resp.llm_reasoning_preview:
        print("LLM REASONING PREVIEW:", resp.llm_reasoning_preview[:300])
    return 0


if __name__ == "__main__":
    sys.exit(main())
