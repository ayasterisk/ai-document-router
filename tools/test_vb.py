"""Test định tuyến trên toàn bộ file PDF trong doc/SoNNMT/vbSoNNMT/.

Luồng (giống production):
  1. extract_pdf_content() -> pdfplumber/pypdf; nếu text < 80 ký tự HOẶC không có
     marker văn bản hành chính (text của chữ ký số) thì OCR.
  2. OCR bản scan = Qwen2.5-VL-3B qua Ollama (OCR_SERVER_URL=http://localhost:11434).
  3. MetadataExtractor + RuleEngine deterministic -> payload 4 trường.

Chạy:  .venv\\Scripts\\python.exe tools\\test_vb.py [--limit N]
Kết quả in đầy đủ 4 trường cho từng văn bản + ghi JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# --- Cấu hình OCR qua Ollama (Qwen2.5-VL-3B) ---
os.environ.setdefault("OCR_SERVER_URL", "http://localhost:11434")
os.environ.setdefault("OCR_MODEL", "qwen2.5vl:3b")
os.environ.setdefault("OCR_PROVIDER", "auto")
os.environ.setdefault("OCR_PAGE_DPI", "150")
os.environ.setdefault("OCR_MAX_TOKENS", "4096")
os.environ.setdefault("OCR_NUM_CTX", "8192")
os.environ.setdefault("OCR_TIMEOUT", "180")

# Windows console (stdout là pipe) mặc định cp1252 -> ép UTF-8 để in tiếng Việt
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.extract.metadata import MetadataExtractor  # noqa: E402
from app.pdf.extractor import (  # noqa: E402
    MIN_TEXT_LENGTH,
    _has_document_content,
    extract_pdf_content,
    extract_text_pdfplumber,
    extract_text_pypdf,
)
from app.rules.engine import Document, RuleEngine  # noqa: E402

VB_DIR = ROOT / "doc" / "SoNNMT" / "vbSoNNMT"
RULES = ROOT / "app" / "rules" / "rules.yaml"
JSON_OUT = ROOT / "tools" / "test_vb_results.json"


def raw_text(path: Path) -> str:
    try:
        t = extract_text_pdfplumber(path)
    except Exception:
        try:
            t = extract_text_pypdf(path)
        except Exception:
            t = ""
    return (t or "").strip()


def _fmt(items) -> str:
    return ", ".join(items) if items else "(rỗng)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="chỉ chạy N file đầu")
    args = ap.parse_args()

    engine = RuleEngine(RULES)
    files = sorted(VB_DIR.glob("*.pdf"))
    if args.limit:
        files = files[: args.limit]

    print(f"=== TEST ĐỊNH TUYẾN — {len(files)} file ===")
    print(f"OCR: {os.environ['OCR_MODEL']} @ {os.environ['OCR_SERVER_URL']}\n")

    n_ocr = 0
    n_review = 0
    n_matched = 0
    results = []
    t0 = time.time()

    for i, f in enumerate(files, 1):
        raw = raw_text(f)
        used_ocr = len(raw) < MIN_TEXT_LENGTH or not _has_document_content(raw)
        text = extract_pdf_content(f)
        meta = MetadataExtractor.extract(text)
        doc = Document(
            so_hieu=meta.so_hieu or "",
            loai=meta.loai or "",
            co_quan_ban_hanh=meta.co_quan_ban_hanh or "",
            nguoi_ky=meta.nguoi_ky or "",
            ngay_van_ban=meta.ngay_van_ban,
            trich_yeu=meta.trich_yeu or "",
            noi_dung=text,
            han_thuc_hien=meta.han_thuc_hien,
            khan=meta.khan,
        )
        res = engine.run(doc)

        if used_ocr:
            n_ocr += 1
        if res.needs_review:
            n_review += 1
        if res.matched_rules:
            n_matched += 1

        tag = "OCR" if used_ocr else "TXT"
        rule = res.matched_rules[0] if res.matched_rules else "—"
        print(f"[{i:02d}/{len(files)}] {tag} {f.name}")
        print(f"  don_vi_xu_ly_chinh : {_fmt(res.don_vi_xu_ly_chinh)}")
        print(f"  phoi_hop_xu_ly     : {_fmt(res.phoi_hop_xu_ly)}")
        print(f"  lanh_dao_theo_doi  : {_fmt(res.lanh_dao_theo_doi)}")
        print(f"  han_thuc_hien      : {res.han_thuc_hien or 'null'}")
        print(f"  matched_rule={rule} | confidence={res.confidence} | needs_review={res.needs_review}")

        results.append(
            {
                "file": f.name,
                "ocr": used_ocr,
                "don_vi_xu_ly_chinh": res.don_vi_xu_ly_chinh,
                "phoi_hop_xu_ly": res.phoi_hop_xu_ly,
                "lanh_dao_theo_doi": res.lanh_dao_theo_doi,
                "han_thuc_hien": res.han_thuc_hien,
                "matched_rules": res.matched_rules,
                "confidence": res.confidence,
                "needs_review": res.needs_review,
                "reason": res.reason,
                "so_hieu": meta.so_hieu,
                "co_quan_ban_hanh": meta.co_quan_ban_hanh,
                "trich_yeu": meta.trich_yeu,
            }
        )

    dt = time.time() - t0
    print("\n=== TỔNG HỢP ===")
    print(f"Tổng file          : {len(files)}")
    print(f"Dùng OCR (scan)    : {n_ocr}")
    print(f"Khớp rule          : {n_matched}")
    print(f"needs_review       : {n_review}")
    print(f"Thời gian          : {dt:.1f}s")

    JSON_OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON đầy đủ: {JSON_OUT}")


if __name__ == "__main__":
    main()
