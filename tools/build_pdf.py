"""Sinh PDF từ rulebaseSoNNMT.md, tái tạo format của rulebaseSoNNMT.pdf (wkhtmltopdf).

Quan sát từ PDF gốc:
  - A4, margin ~4mm, body DejaVuSans 6.9pt màu #1F2937
  - H1 #0B3D2E 12.7pt / H2 #0B5D43 9.8pt / H3 #14532D 8.1pt
  - <strong> màu #0B3D2E; <em> màu #4B5563
  - bảng viền #CCD6E0, header nền nhạt #F2F5F2 chữ #0B3D2E 6.3pt
  - code/pre nền #F7F9FA; blockquote nền #E8F0E8 viền trái xanh

Đầu ra: tools/rulebase.html (dùng Chrome headless in ra PDF).
"""
from __future__ import annotations

from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "doc" / "SoNNMT" / "rulebaseSoNNMT.md"
OUT_HTML = ROOT / "tools" / "rulebase.html"

CSS = """
@page { size: A4; margin: 4mm; }
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body { margin: 0; padding: 0; }
body {
  font-family: 'DejaVu Sans', 'Segoe UI', Arial, sans-serif;
  font-size: 6.9pt;
  line-height: 1.45;
  color: #1F2937;
}
h1 { font-size: 12.7pt; color: #0B3D2E; margin: 0 0 6px 0; font-weight: bold; }
h2 { font-size: 9.8pt; color: #0B5D43; margin: 10px 0 4px 0; font-weight: bold;
     border-bottom: 1px solid #CCD6E0; padding-bottom: 2px; }
h3 { font-size: 8.1pt; color: #14532D; margin: 8px 0 3px 0; font-weight: bold; }
p { margin: 4px 0; }
strong { color: #0B3D2E; }
em { color: #4B5563; }
hr { border: none; border-top: 1px solid #CCD6E0; margin: 8px 0; }
ul, ol { margin: 4px 0 4px 18px; padding: 0; }
li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 5px 0; }
th, td { border: 1px solid #CCD6E0; padding: 2.5px 5px; font-size: 6.3pt;
         text-align: left; vertical-align: top; }
th { background: #F2F5F2; color: #0B3D2E; font-weight: bold; }
tr { page-break-inside: avoid; }
pre { background: #F7F9FA; border: 1px solid #CCD6E0; padding: 6px 8px;
      font-size: 6.3pt; line-height: 1.35; white-space: pre-wrap; word-wrap: break-word; }
code { font-family: 'Consolas', 'DejaVu Sans Mono', monospace; font-size: 6.3pt;
       background: #F2F5F2; padding: 0 2px; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #0B5D43; background: #E8F0E8; margin: 6px 0;
             padding: 3px 8px; color: #1F2937; }
blockquote p { margin: 2px 0; }
"""


def main() -> None:
    md_text = MD.read_text(encoding="utf-8")
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html_doc = (
        "<!DOCTYPE html>\n"
        '<html lang="vi"><head><meta charset="utf-8">'
        f"<style>{CSS}</style></head>\n"
        f"<body>\n{body}\n</body></html>"
    )
    OUT_HTML.write_text(html_doc, encoding="utf-8")
    print(f"wrote {OUT_HTML} ({len(html_doc)} bytes)")


if __name__ == "__main__":
    main()
