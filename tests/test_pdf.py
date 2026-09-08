"""Real mixed PDF plus controlled OCR failures; no network or model needed."""

import io
import unittest
from unittest.mock import Mock, patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.pdf.extractor import (
    PdfInputError,
    extract_pdf_result_bytes,
    quality_ok,
)

VALID = "V/v bao cao cong trinh thuy loi. Noi dung van ban gui den co quan quan ly de xem xet va phoi hop xu ly dung thoi han quy dinh."


def pdf_bytes(pages):
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=595, height=842)
        if text:
            font = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): writer._add_object(font)}
                    )
                }
            )
            stream = DecodedStreamObject()
            stream.set_data(
                ("BT /F1 11 Tf 20 750 Td (" + text + ") Tj ET").encode("ascii")
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class PdfTests(unittest.TestCase):
    def test_quality_rejects_garbage(self):
        for text in ["@@@@", "a" * 200, "(cid:23)" * 30, "word " * 50]:
            self.assertFalse(quality_ok(text))
        self.assertTrue(quality_ok(VALID))

    def test_mixed_pages_ocr_only_missing_page_and_fallback(self):
        with (
            patch.dict("os.environ", {"OCR_PROVIDER": "auto"}),
            patch("app.pdf.extractor._raster_page", return_value=Mock()) as raster,
            patch("app.pdf.extractor._qwen_image", return_value="@@@@") as qwen,
            patch("app.pdf.extractor._tesseract_image", return_value=VALID) as fallback,
        ):
            result = extract_pdf_result_bytes(pdf_bytes([VALID, None]))
        self.assertEqual(len(result.pages), 2)
        self.assertEqual(raster.call_count, 1)
        self.assertEqual(qwen.call_count, 1)
        self.assertEqual(fallback.call_count, 1)
        self.assertEqual(result.pages[1].provider, "tesseract")
        self.assertFalse(result.needs_review)

    def test_failed_page_is_not_silently_dropped(self):
        with patch.dict("os.environ", {"OCR_PROVIDER": "none"}):
            result = extract_pdf_result_bytes(pdf_bytes([VALID, None]))
        self.assertTrue(result.needs_review)
        self.assertEqual(len(result.pages), 2)
        self.assertEqual(result.pages[1].status, "needs_review")

    def test_page_and_signature_limits(self):
        with self.assertRaises(PdfInputError):
            extract_pdf_result_bytes(b"bad")
        with self.assertRaisesRegex(PdfInputError, "page_limit"):
            extract_pdf_result_bytes(pdf_bytes([None, None]), max_pages=1)

    def test_truncated_model_output_rejected(self):
        from app.pdf.extractor import _qwen_image

        response = Mock()
        response.json.return_value = {
            "choices": [{"finish_reason": "length", "message": {"content": VALID}}]
        }
        image = Mock()
        image.convert.return_value.save.side_effect = lambda buf, format: buf.write(
            b"image"
        )
        with (
            patch.dict("os.environ", {"OCR_SERVER_URL": "http://unused"}),
            patch("httpx.post", return_value=response),
            self.assertRaisesRegex(RuntimeError, "incomplete_ocr"),
        ):
            _qwen_image(image)


if __name__ == "__main__":
    unittest.main()
