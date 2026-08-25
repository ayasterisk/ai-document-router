"""Trích xuất nội dung text từ PDF, có hook OCR cho bản scan."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 50  # ngưỡng coi text extract là "quá ít" -> kích hoạt OCR


def extract_text_pdfplumber(path: Path) -> str:
    """Dùng pdfplumber để trích text (PDF text-based)."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                parts.append(text)
    return "\n".join(parts)


def extract_text_pypdf(path: Path) -> str:
    """Fallback bằng pypdf khi pdfplumber thất bại."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def ocr_pdf(path: Path) -> str:
    """OCR bản scan bằng Tesseract (offline).

    Là hook: cài `pytesseract` + binary Tesseract để dùng thật.
    Trả về chuỗi rỗng nếu chưa cài đặt — caller tự quyết định fallback tiếp theo.
    """
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        logger.warning("pytesseract/pdf2image chưa cài — bỏ qua OCR")
        return ""

    try:
        images = convert_from_path(str(path))
        return "\n".join(pytesseract.image_to_string(img, lang="vie") for img in images)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR thất bại: %s", exc)
        return ""


def extract_pdf_content(path: Path, ocr_fallback: bool = True) -> str:
    """Trích text từ PDF; nếu quá ít thì thử OCR (nếu bật)."""
    text = ""
    try:
        text = extract_text_pdfplumber(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdfplumber thất bại (%s), thử pypdf", exc)
        try:
            text = extract_text_pypdf(path)
        except Exception as exc2:  # noqa: BLE001
            logger.warning("pypdf thất bại (%s)", exc2)

    text = (text or "").strip()

    if len(text) < MIN_TEXT_LENGTH and ocr_fallback:
        logger.info("Text quá ít (%d ký tự), thử OCR", len(text))
        ocr_text = ocr_pdf(path).strip()
        if ocr_text:
            text = ocr_text

    return text


def extract_pdf_content_bytes(data: bytes, ocr_fallback: bool = True) -> str:
    """Trích text từ nội dung PDF dạng bytes (dùng cho upload trực tiếp)."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return extract_pdf_content(tmp_path, ocr_fallback=ocr_fallback)
    finally:
        tmp_path.unlink(missing_ok=True)
