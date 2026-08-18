# -*- coding: utf-8 -*-
"""Chuyển rulebaseSoNNMT.md -> HTML -> PDF (dùng Chrome headless)."""
import pathlib
import subprocess
import sys

import markdown

BASE = pathlib.Path(__file__).resolve().parent
MD = BASE / "rulebaseSoNNMT.md"
HTML = BASE / "rulebaseSoNNMT.html"
PDF = BASE / "rulebaseSoNNMT.pdf"

CSS = """
@page { size: A4; margin: 15mm 14mm; }
* { box-sizing: border-box; }
body {
    font-family: 'Segoe UI', 'Arial', 'Helvetica Neue', sans-serif;
    font-size: 12px;
    line-height: 1.55;
    color: #1f2937;
    margin: 0;
}
h1 {
    font-size: 22px;
    color: #0b3d2e;
    border-bottom: 3px solid #0b3d2e;
    padding-bottom: 8px;
    margin: 0 0 6px;
}
h2 {
    font-size: 17px;
    color: #0b5d43;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 5px;
    margin: 22px 0 10px;
}
h3 {
    font-size: 14px;
    color: #14532d;
    margin: 16px 0 8px;
}
h4, h5 { font-size: 12px; margin: 12px 0 6px; }
p { margin: 6px 0; }
strong { color: #0b3d2e; }
em { color: #4b5563; }
ul, ol { margin: 6px 0; padding-left: 22px; }
li { margin: 3px 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 10px 0;
    font-size: 11px;
    page-break-inside: auto;
}
tr { page-break-inside: avoid; }
th, td {
    border: 1px solid #cbd5e1;
    padding: 5px 7px;
    text-align: left;
    vertical-align: top;
}
th {
    background: #e7f0ea;
    color: #0b3d2e;
    font-weight: 600;
}
tr:nth-child(even) td { background: #f8fafc; }
code {
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 10.5px;
    background: #f1f5f9;
    padding: 1px 4px;
    border-radius: 3px;
}
pre {
    background: #f6f8fa;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #0b5d43;
    padding: 10px 12px;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-size: 10.5px;
    page-break-inside: avoid;
}
pre code { background: none; padding: 0; }
blockquote {
    border-left: 4px solid #0b5d43;
    background: #f0fdf4;
    margin: 10px 0;
    padding: 8px 12px;
    color: #14532d;
}
hr { border: none; border-top: 1px solid #cbd5e1; margin: 16px 0; }
"""


def main() -> int:
    md_text = MD.read_text(encoding="utf-8")
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html = (
        "<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'>"
        f"<title>RULEBASE PHÂN LUỒNG, CHUYỂN VĂN BẢN ĐẾN</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    HTML.write_text(html, encoding="utf-8")
    print(f"HTML: {HTML}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
