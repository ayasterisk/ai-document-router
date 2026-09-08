"""PDF routing diagnostics. Match counts are NOT business accuracy.

Default: text layers only, no network. Pass --ocr to use configured OCR providers.
For accuracy against adjudicated labels use tools/evaluate.py.
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.orchestrator.harness import Harness
from app.pdf.extractor import PdfInputError, extract_pdf_result
from app.rules.engine import RuleEngine

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument(
        "--received-on", type=date.fromisoformat, default=date(2026, 9, 8)
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/pdf-diagnostics.json"
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    harness = Harness(RuleEngine(settings.rules_path), mode="off")
    files = sorted((ROOT / "doc/SoNNMT/vbSoNNMT").glob("*.pdf"))
    if args.limit:
        files = files[: args.limit]
    results = []
    for path in files:
        try:
            extraction = extract_pdf_result(
                path, ocr_fallback=args.ocr, max_pages=settings.max_pages
            )
            result = harness.run(extraction.text, today=args.received_on)
            if extraction.needs_review:
                result.needs_review = True
                result.review_reasons.append("incomplete_or_unverified_extraction")
            results.append(
                {
                    "file": path.name,
                    "extraction": extraction.metadata(),
                    "result": asdict(result),
                }
            )
        except PdfInputError as exc:
            results.append({"file": path.name, "error": str(exc)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"purpose": "diagnostic_only_not_accuracy", "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Wrote diagnostics for {len(results)} PDFs; this is not an accuracy measurement."
    )
