"""Trích xuất nội dung văn bản từ PDF.

Chiến lược (theo doc/thiet-ke-ai-document-router.md Mục 6):
  1. pypdf — nhanh, đủ dùng cho PDF text-based (đầu vào chủ yếu của dự án).
  2. pdfplumber — fallback khi pypdf trả quá ít text (font/encoding phức tạp).
  3. Trả về rỗng + cờ cần OCR nếu cả hai không ra text — để sẵn hook OCR.
"""

import io
from typing import Tuple


def extract_text_from_bytes(data: bytes, max_chars: int = 20000) -> Tuple[str, str, bool]:
    """Trả (text, engine_used, need_ocr).

    need_ocr=True khi PDF có vẻ là bản scan (không trích được text).
    """
    text = _try_pypdf(data)
    engine = "pypdf"
    if len(text.strip()) < 20:
        text2 = _try_pdfplumber(data)
        if len(text2.strip()) > len(text.strip()):
            text, engine = text2, "pdfplumber"

    text = text[:max_chars] if max_chars else text
    need_ocr = len(text.strip()) < 20
    return text.strip(), engine, need_ocr


def extract_text_from_file(path: str, max_chars: int = 20000) -> Tuple[str, str, bool]:
    with open(path, "rb") as f:
        return extract_text_from_bytes(f.read(), max_chars=max_chars)


def _try_pypdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(parts)
    except Exception:
        return ""


def _try_pdfplumber(data: bytes) -> str:
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts = []
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)
    except Exception:
        return ""


# Hook OCR — triển khai sau nếu gặp bản scan (Tesseract hoặc model vision).
def ocr_hook(data: bytes) -> str:
    """Chưa triển khai mặc định — nơi cắm OCR cho PDF dạng scan."""
    return ""
