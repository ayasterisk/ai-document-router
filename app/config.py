"""Configuration; secrets live in environment or .env, never in the repository."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    api_keys: dict[str, str] = field(default_factory=dict)  # principal -> token
    allowed_origins: list[str] = field(default_factory=list)
    db_path: Path = ROOT / "app/storage/audit.db"
    rules_path: Path = ROOT / "app/rules/rules.yaml"
    directory_path: Path = ROOT / "app/rules/directory.json"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_text_chars: int = 200_000
    max_pages: int = 50
    max_files: int = 5
    max_workers: int = 2
    max_pending: int = 8
    job_timeout: int = 300
    retention_days: int = 30

    def validate(self):
        if not self.api_keys or any(
            not name
            or not isinstance(token, str)
            or len(token) < 32
            or token.startswith("REPLACE_")
            for name, token in self.api_keys.items()
        ):
            raise ValueError(
                "ROUTER_API_KEYS must contain principal names and tokens of at least 32 characters"
            )
        if len(set(self.api_keys.values())) != len(self.api_keys):
            raise ValueError("Each principal must have a distinct API token")
        if "*" in self.allowed_origins:
            raise ValueError("Use explicit allowed origins")
        for name in (
            "max_upload_bytes",
            "max_text_chars",
            "max_pages",
            "max_files",
            "max_workers",
            "max_pending",
            "job_timeout",
            "retention_days",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
        result = cls(
            api_keys=json.loads(os.getenv("ROUTER_API_KEYS", "{}")),
            allowed_origins=json.loads(os.getenv("ROUTER_ALLOWED_ORIGINS", "[]")),
            db_path=Path(
                os.getenv("ROUTER_DB_PATH", str(ROOT / "app/storage/audit.db"))
            ),
        )
        for name in (
            "max_upload_bytes",
            "max_text_chars",
            "max_pages",
            "max_files",
            "max_workers",
            "max_pending",
            "job_timeout",
            "retention_days",
        ):
            setattr(
                result,
                name,
                int(os.getenv("ROUTER_" + name.upper(), str(getattr(result, name)))),
            )
        return result
