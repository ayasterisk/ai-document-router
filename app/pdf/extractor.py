"""Trích xuất nội dung text từ PDF.

Chiến lược OCR 3 tầng (xem doc/ke-hoach-thuc-hien.md — Hạ tầng GPU & OCR):
  1. PDF text-based -> pdfplumber/pypdf (nhanh, không cần GPU).
  2. Bản scan -> OCR. Thứ tự ưu tiên cấu hình qua biến môi trường OCR_PROVIDER:
       - qwen-vl   : Qwen2.5-VL-7B-Instruct qua vLLM (API tương thích OpenAI) — chất lượng cao.
       - tesseract : Tesseract offline — rẻ, không cần GPU, dùng làm fallback.
       - auto      : thử qwen-vl trước, rồi tesseract.
       - none      : tắt OCR.
  3. Không OCR được -> trả text rỗng/ngắn, caller tự quyết định báo lỗi / needs_review.
"""
from __future__ import annotations

import base64
import io
import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 50  # ngưỡng coi text extract là "quá ít" -> kích hoạt OCR


# --------------------------------------------------------------------------- #
# Cấu hình OCR (đọc từ env, có default)
# --------------------------------------------------------------------------- #
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


OCR_PROVIDER = _env("OCR_PROVIDER", "auto").lower()  # auto | qwen-vl | tesseract | none
OCR_SERVER_URL = _env("OCR_SERVER_URL", "").rstrip("/")
OCR_MODEL = _env("OCR_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct")
OCR_API_KEY = _env("OCR_API_KEY", "EMPTY")
OCR_PAGE_DPI = int(os.getenv("OCR_PAGE_DPI", "200"))
OCR_MAX_TOKENS = int(os.getenv("OCR_MAX_TOKENS", "8192"))
OCR_TIMEOUT = float(os.getenv("OCR_TIMEOUT", "120"))

OCR_USER_PROMPT = (
    "Đây là ảnh quét một trang văn bản hành chính tiếng Việt. "
    "Hãy trích xuất TOÀN BỘ văn bản trong ảnh (tiêu đề, số hiệu, nội dung, bảng, chữ ký), "
    "giữ nguyên thứ tự và xuống dòng theo bố cục, không tóm tắt, không bình luận, "
    "chỉ trả về phần chữ trong trang."
)


# --------------------------------------------------------------------------- #
# Trích text PDF (born-digital)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# OCR — Tesseract (fallback offline)
# --------------------------------------------------------------------------- #
def ocr_tesseract(path: Path) -> str:
    """OCR bản scan bằng Tesseract (offline).

    Cần cài `pytesseract` + binary Tesseract (+ lang data "vie").
    Trả chuỗi rỗng nếu chưa cài đặt — caller tự quyết định fallback tiếp theo.
    """
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        logger.warning("pytesseract/pdf2image chưa cài — bỏ qua OCR tesseract")
        return ""

    try:
        images = convert_from_path(str(path))
        return "\n".join(pytesseract.image_to_string(img, lang="vie") for img in images)
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR tesseract thất bại: %s", exc)
        return ""


def ocr_pdf(path: Path) -> str:
    """Alias giữ tương thích — OCR Tesseract."""
    return ocr_tesseract(path)


# --------------------------------------------------------------------------- #
# OCR — Qwen2.5-VL-7B-Instruct qua vLLM (OpenAI-compatible)
# --------------------------------------------------------------------------- #
def ocr_qwen_vl(path: Path) -> str:
    """OCR từng trang bằng Qwen2.5-VL-7B phục vụ qua vLLM.

    Yêu cầu:
      - vLLM đang chạy model Qwen2.5-VL-7B-Instruct (đặt OCR_SERVER_URL).
      - Client cài `pdf2image` (+ Poppler) và `Pillow`.
    Trả chuỗi rỗng nếu thiếu cấu hình/thư viện — caller fallback tiếp.
    """
    if not OCR_SERVER_URL:
        logger.info("Chưa đặt OCR_SERVER_URL — bỏ qua OCR qwen-vl")
        return ""

    try:
        from pdf2image import convert_from_path  # type: ignore
    except ImportError:
        logger.warning("pdf2image chưa cài (cần Poppler) — không dùng OCR qwen-vl")
        return ""

    try:
        import httpx
    except ImportError:
        logger.warning("httpx chưa cài — không dùng OCR qwen-vl")
        return ""

    try:
        images = convert_from_path(str(path), dpi=OCR_PAGE_DPI)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không rasterize được PDF (%s)", exc)
        return ""

    parts: list[str] = []
    for page_no, img in enumerate(images, start=1):
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        payload = {
            "model": OCR_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_USER_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": OCR_MAX_TOKENS,
        }

        try:
            resp = httpx.post(
                f"{OCR_SERVER_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {OCR_API_KEY}"},
                json=payload,
                timeout=OCR_TIMEOUT,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR qwen-vl trang %d thất bại: %s", page_no, exc)
            content = ""

        if content:
            parts.append(content.strip())

    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Chuỗi OCR ưu tiên
# --------------------------------------------------------------------------- #
def _ocr_chain() -> List[str]:
    if OCR_PROVIDER == "none":
        return []
    if OCR_PROVIDER == "tesseract":
        return ["tesseract"]
    if OCR_PROVIDER == "qwen-vl":
        return ["qwen-vl"]
    # auto: VLM trước (chất lượng cao) -> tesseract fallback
    return ["qwen-vl", "tesseract"]


def _run_ocr(provider: str, path: Path) -> str:
    if provider == "qwen-vl":
        return ocr_qwen_vl(path).strip()
    return ocr_tesseract(path).strip()


# --------------------------------------------------------------------------- #
# Entrypoints
# --------------------------------------------------------------------------- #
def extract_pdf_content(path: Path, ocr_fallback: bool = True) -> str:
    """Trích text từ PDF; nếu quá ít thì chạy chuỗi OCR (nếu bật)."""
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

    if len(text) >= MIN_TEXT_LENGTH or not ocr_fallback:
        return text

    logger.info("Text quá ít (%d ký tự), kích hoạt OCR (provider=%s)", len(text), OCR_PROVIDER)
    for provider in _ocr_chain():
        try:
            ocr_text = _run_ocr(provider, path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("OCR %s lỗi: %s", provider, exc)
            ocr_text = ""
        if ocr_text:
            logger.info("OCR %s trả %d ký tự", provider, len(ocr_text))
            return ocr_text

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
