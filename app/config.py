"""Cấu hình server — đọc từ .env (xem .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # không ghi đè biến môi trường đã có


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    # --- DeepSeek (OpenAI-compatible) ---
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
    DEEPSEEK_BASE_URL: str = (
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        or "https://api.deepseek.com"
    )
    # Core model theo yêu cầu dự án: deepseek-reasoner.
    # Có thể đổi sang deepseek-chat / deepseek-v4-flash / deepseek-v4-pro qua .env.
    DEEPSEEK_MODEL: str = (
        os.getenv("DEEPSEEK_MODEL", "deepseek-reasoner").strip()
        or "deepseek-reasoner"
    )
    DEEPSEEK_MAX_TOKENS: int = _env_int("DEEPSEEK_MAX_TOKENS", 8192)
    LLM_TIMEOUT: int = _env_int("LLM_TIMEOUT", 120)

    # --- Server ---
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = _env_int("PORT", 8000)

    # --- Harness ---
    RULE_CONFIDENCE_HIGH: float = _env_float("RULE_CONFIDENCE_HIGH", 0.80)
    RULE_CONFIDENCE_LOW: float = _env_float("RULE_CONFIDENCE_LOW", 0.50)
    ALLOW_LLM: bool = os.getenv("ALLOW_LLM", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "",
    )

    # --- Audit ---
    AUDIT_DB_PATH: str = os.getenv(
        "AUDIT_DB_PATH", str(BASE_DIR / "app" / "storage" / "audit.db")
    )

    # --- PDF ---
    PDF_MAX_CHARS: int = _env_int("PDF_MAX_CHARS", 20000)

    # Các file tài liệu nạp vào context LLM (không sửa, chỉ đọc)
    RULEBASE_PATH: Path = BASE_DIR / "doc" / "rulebase.md"
    TU_DIEN_PATH: Path = BASE_DIR / "doc" / "tu-dien-linh-vuc.yaml"
    RULES_YAML_PATH: Path = Path(__file__).parent / "rules" / "rules.yaml"

    @property
    def llm_available(self) -> bool:
        return bool(self.DEEPSEEK_API_KEY)


settings = Settings()
