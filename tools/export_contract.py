"""Export the actual OpenAPI contract and a deterministic example, without network."""

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Do not let the example contact a configured model/OCR server.
os.environ["HARNESS_TOOL_MODE"] = "off"
os.environ["INFERENCE_SERVER_URL"] = ""
os.environ["OCR_PROVIDER"] = "none"
from app.config import Settings
from app.main import create_app
from app.models.directory import Directory
from app.rules.engine import RuleEngine
from app.worker import classify_payload

if __name__ == "__main__":
    settings = Settings()
    engine = RuleEngine(settings.rules_path)
    directory = Directory(settings.directory_path)
    text = "UBND tỉnh Gia Lai\nSố: 12/UBND-NNMT\nGia Lai, ngày 8 tháng 9 năm 2026\nCÔNG VĂN\nV/v xây dựng công trình thủy lợi\nKính gửi: Sở Nông nghiệp và Môi trường\nĐề nghị hoàn thành trước ngày 10/09/2026."
    digest = hashlib.sha256(
        json.dumps(
            {"text": text, "files": []}, ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    result = classify_payload(
        {
            "job_id": "example-job",
            "document_id": "9634",
            "received_on": "2026-09-08",
            "text": text,
            "files": [],
            "input_sha256": digest,
            "rules_path": str(settings.rules_path),
            "rules_sha256": engine.fingerprint,
            "directory_path": str(settings.directory_path),
            "directory_version": directory.version,
            "max_pages": 50,
            "max_text_chars": 200000,
        }
    )
    (ROOT / "doc/openapi.json").write_text(
        json.dumps(create_app(settings).openapi(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ROOT / "doc/api-example-response.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
