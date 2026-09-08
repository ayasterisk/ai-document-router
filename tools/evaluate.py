"""Evaluate all four routing fields; proposed labels never count as approved accuracy."""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.orchestrator.harness import Harness
from app.pdf.extractor import extract_pdf_result
from app.rules.engine import Document, RuleEngine

FIELDS = ("don_vi_xu_ly_chinh", "phoi_hop_xu_ly", "lanh_dao_theo_doi", "han_thuc_hien")


def evaluate(dataset, mode="excerpt", include_proposed=False):
    engine = RuleEngine(ROOT / "app/rules/rules.yaml")
    rows = []
    for case in dataset["cases"]:
        expected = case.get("expected")
        if expected is None or (
            case["label_status"] != "business_approved" and not include_proposed
        ):
            continue
        today = date.fromisoformat(case["received_on"])
        if mode == "pdf":
            extraction = extract_pdf_result(ROOT / case["file"])
            actual = Harness(engine, mode="off").run(extraction.text, today)
            actual.needs_review |= extraction.needs_review
        else:
            actual = engine.run(Document(**case["document"]), today)
        match = {
            field: (
                set(getattr(actual, field)) == set(expected[field])
                if field != "han_thuc_hien"
                else getattr(actual, field) == expected[field]
            )
            for field in FIELDS
        }
        rows.append(
            {
                "id": case["id"],
                "label_status": case["label_status"],
                "field_match": match,
                "exact_match": all(match.values()),
                "needs_review": actual.needs_review,
                "matched_rules": actual.matched_rules,
                "actual": {f: getattr(actual, f) for f in FIELDS},
            }
        )
    n = len(rows)
    auto = [r for r in rows if not r["needs_review"]]
    return {
        "mode": mode,
        "label_scope": "proposed_included"
        if include_proposed
        else "business_approved_only",
        "rules_sha256": engine.fingerprint,
        "evaluated": n,
        "skipped": len(dataset["cases"]) - n,
        "exact_four_field_accuracy": sum(r["exact_match"] for r in rows) / n
        if n
        else None,
        "field_accuracy": {
            f: sum(r["field_match"][f] for r in rows) / n if n else None for f in FIELDS
        },
        "review_rate": sum(r["needs_review"] for r in rows) / n if n else None,
        "error_rate_without_review": sum(not r["exact_match"] for r in auto) / len(auto)
        if auto
        else None,
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "tests/gold/sonnmt.json")
    parser.add_argument("--mode", choices=["excerpt", "pdf"], default="excerpt")
    parser.add_argument("--include-proposed", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(
        json.loads(args.dataset.read_text(encoding="utf-8")),
        args.mode,
        args.include_proposed,
    )
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(content)
