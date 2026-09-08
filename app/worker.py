"""Isolated worker entrypoint. One subprocess per job provides a hard time budget."""

from __future__ import annotations

import base64
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from app.config import ROOT
from app.models.directory import Directory
from app.models.schema import ROLES, ClassifyResponse
from app.orchestrator.harness import Harness, HttpInferenceClient
from app.pdf.extractor import PdfInputError, extract_pdf_result_bytes
from app.rules.engine import RuleEngine


def classify_payload(payload, include_audit=False):
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    engine = RuleEngine(payload["rules_path"])
    directory = Directory(Path(payload["directory_path"]))
    if (
        engine.fingerprint != payload["rules_sha256"]
        or directory.version != payload["directory_version"]
    ):
        raise ValueError("configuration_changed")
    extraction = {"files": [], "needs_review": False}
    text = payload.get("text", "")
    if payload.get("files"):
        sections = []
        page_count = 0
        for item in payload["files"]:
            result = extract_pdf_result_bytes(
                base64.b64decode(item["base64"], validate=True),
                max_pages=payload["max_pages"] - page_count,
            )
            page_count += len(result.pages)
            sections.append(result.text)
            extraction["files"].append(
                {"name": item["name"], "sha256": item["sha256"], **result.metadata()}
            )
            extraction["needs_review"] |= result.needs_review
        text = "\n\f\n".join(sections)
    if not text.strip():
        raise PdfInputError("no_document_content")
    if len(text) > payload["max_text_chars"]:
        raise PdfInputError("extracted_text_limit_exceeded")
    url = os.getenv("INFERENCE_SERVER_URL")
    client = (
        HttpInferenceClient(
            url,
            api_key=os.getenv("INFERENCE_API_KEY", "EMPTY"),
            model=os.getenv("INFERENCE_MODEL", "default"),
            supports_tool_calling=os.getenv("INFERENCE_TOOL_CALLING", "true") == "true",
        )
        if url
        else None
    )
    harness = Harness(engine, client, mode=os.getenv("HARNESS_TOOL_MODE", "auto"))
    result = harness.run(text, today=date.fromisoformat(payload["received_on"]))
    if extraction["needs_review"]:
        result.needs_review = True
        result.review_reasons.append("incomplete_or_unverified_extraction")
    if len(payload.get("files", [])) > 1:
        result.needs_review = True
        result.review_reasons.append("multiple_attachments_require_review")
    result.evidence["runtime"] = {
        "inference_model": getattr(client, "model", None),
        "prompt_version": "2.0",
        "ocr_model": os.getenv("OCR_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"),
        "ocr_provider": os.getenv("OCR_PROVIDER", "auto"),
    }
    response = ClassifyResponse(
        **asdict(result),
        job_id=payload["job_id"],
        document_id=payload["document_id"],
        input_sha256=payload["input_sha256"],
        rules_version=engine.version,
        rules_sha256=engine.fingerprint,
        directory_version=directory.version,
        received_on=payload["received_on"],
        extraction=extraction,
        recipients={role: directory.resolve(getattr(result, role)) for role in ROLES},
    )
    result = response.model_dump(mode="json")
    return (result, text) if include_audit else result


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        result, text = classify_payload(json.load(sys.stdin), include_audit=True)
        print(json.dumps({"result": result, "audit_text": text}, ensure_ascii=False))
    except (ValueError, PdfInputError) as exc:
        # Controlled codes only; never return document text or server internals.
        allowed = {
            "invalid_pdf",
            "invalid_pdf_signature",
            "encrypted_pdf",
            "page_limit_exceeded",
            "no_document_content",
            "extracted_text_limit_exceeded",
            "configuration_changed",
        }
        print(
            json.dumps(
                {"error": str(exc) if str(exc) in allowed else "invalid_document"}
            )
        )
    except Exception:  # noqa: BLE001 - isolate provider/job failures and record status
        print(json.dumps({"error": "processing_failed"}))


if __name__ == "__main__":
    main()
