# -*- coding: utf-8 -*-
"""Generate a styled PDF (v2) from rulebaseSoNNMT.md using Chrome headless."""
import html
import subprocess
import sys
from pathlib import Path

import markdown

BASE_DIR = Path(__file__).resolve().parent
MD_FILE = BASE_DIR / "rulebaseSoNNMT.md"
OUT_HTML = BASE_DIR / "rulebaseSoNNMT-v2.html"
OUT_PDF = BASE_DIR / "rulebaseSoNNMT-v2.pdf"

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

CSS = """
@page {
  size: A4;
  margin: 14mm;
}

* {
  box-sizing: border-box;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

body {
  font-family: "Segoe UI", "Segoe UI Symbol", Arial, sans-serif;
  font-size: 9pt;
  line-height: 1.5;
  color: #1F2937;
  margin: 0;
}

h1 {
  font-size: 16.5pt;
  font-weight: 700;
  color: #0B3D2E;
  border-bottom: 2px solid #0B3D2E;
  padding-bottom: 6px;
  margin: 0 0 14px 0;
}

h2 {
  font-size: 12.8pt;
  font-weight: 700;
  color: #0B5D43;
  border-bottom: 1px solid #CBD5E1;
  padding-bottom: 3px;
  margin: 16px 0 8px 0;
  page-break-after: avoid;
}

h3 {
  font-size: 10.5pt;
  font-weight: 700;
  color: #14532D;
  margin: 12px 0 4px 0;
  page-break-after: avoid;
}

p { margin: 4px 0; }

strong { font-weight: 700; color: #0B3D2E; }

em { font-style: italic; color: #4B5563; }

hr {
  border: none;
  border-top: 1px solid #CBD5E1;
  margin: 12px 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 8.2pt;
  page-break-inside: auto;
}

th, td {
  border: 1px solid #CBD5E1;
  padding: 4px 6px;
  vertical-align: top;
  text-align: left;
}

thead { display: table-header-group; }

th {
  background: #E7F0E9;
  color: #0B3D2E;
  font-weight: 600;
}

td { background: #F7FAFB; }

pre {
  background: #F5F7FA;
  border: 1px solid #E2E7F0;
  border-left: 3px solid #0B5D43;
  padding: 8px 10px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 7.9pt;
  line-height: 1.5;
  color: #1F2937;
  white-space: pre;
  overflow-x: auto;
  margin: 8px 0;
}

code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 7.9pt;
  background: #F5F7FA;
  padding: 0 3px;
  color: #1F2937;
}

pre code {
  background: none;
  padding: 0;
}

blockquote {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #0B5D43;
  background: #F0FDF4;
  color: #14532D;
}

blockquote p { margin: 2px 0; }

ul, ol {
  margin: 4px 0 8px 0;
  padding-left: 0;
  list-style-position: inside;
}

li { margin: 2px 0; }
"""


def md_to_html(text: str) -> str:
    return markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )


def main() -> None:
    raw = MD_FILE.read_text(encoding="utf-8")

    # Extract the first H1 as the document title (for PDF metadata only).
    title = "RULEBASE PHÂN LUỒNG, CHUYỂN VĂN BẢN ĐẾN"
    for line in raw.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    body = md_to_html(raw)

    doc = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""

    OUT_HTML.write_text(doc, encoding="utf-8")

    cmd = [
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        "--print-to-pdf-no-header",
        f"--print-to-pdf={OUT_PDF}",
        OUT_HTML.as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"Generated: {OUT_PDF}")


if __name__ == "__main__":
    sys.exit(main())
