"""Convert LangGraph-Orchestration-Analysis.md to PDF."""
from __future__ import annotations

import re
from pathlib import Path

import markdown
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "LangGraph-Orchestration-Analysis.md"
PDF_PATH = ROOT / "LangGraph-Orchestration-Analysis.pdf"

CSS = """
@page {
    size: A4;
    margin: 2cm 1.8cm;
    @frame footer {
        -pdf-frame-content: footerContent;
        bottom: 0.5cm;
        margin-left: 1.8cm;
        margin-right: 1.8cm;
        height: 1cm;
    }
}
body {
    font-family: Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.45;
    color: #1a1a1a;
}
h1 {
    font-size: 20pt;
    color: #0f172a;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 6px;
    margin-top: 24px;
}
h2 {
    font-size: 14pt;
    color: #1e3a5f;
    margin-top: 20px;
    border-bottom: 1px solid #cbd5e1;
    padding-bottom: 4px;
}
h3 {
    font-size: 11pt;
    color: #334155;
    margin-top: 14px;
}
h4 {
    font-size: 10pt;
    color: #475569;
    margin-top: 10px;
}
p, li {
    margin-bottom: 6px;
}
ul, ol {
    margin-left: 16px;
}
code {
    font-family: Courier, monospace;
    font-size: 8.5pt;
    background-color: #f1f5f9;
    padding: 1px 3px;
}
pre {
    font-family: Courier, monospace;
    font-size: 8pt;
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 8px;
    white-space: pre-wrap;
    word-wrap: break-word;
    line-height: 1.3;
}
table {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0 14px 0;
    font-size: 9pt;
}
th {
    background-color: #1e40af;
    color: white;
    padding: 6px 8px;
    text-align: left;
}
td {
    border: 1px solid #cbd5e1;
    padding: 5px 8px;
    vertical-align: top;
}
tr:nth-child(even) td {
    background-color: #f8fafc;
}
blockquote {
    border-left: 3px solid #2563eb;
    margin: 10px 0;
    padding: 4px 12px;
    color: #475569;
    background-color: #f8fafc;
}
hr {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 16px 0;
}
a {
    color: #2563eb;
    text-decoration: none;
}
.mermaid-note {
    font-style: italic;
    color: #64748b;
    font-size: 9pt;
    margin-bottom: 6px;
}
"""


def preprocess_mermaid(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        return (
            "\n\n*[Diagram — see markdown source for mermaid rendering]*\n\n"
            f"```\n{body}\n```\n\n"
        )

    return re.sub(r"```mermaid\n(.*?)```", repl, text, flags=re.DOTALL)


def md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    md_text = preprocess_mermaid(md_text)

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8"/>
    <title>DataMind AI — LangGraph Orchestration Analysis</title>
    <style>{CSS}</style>
</head>
<body>
{html_body}
<div id="footerContent" style="font-size:8pt;color:#94a3b8;text-align:center;">
    DataMind AI — LangGraph Orchestration Analysis | Generated June 2026
</div>
</body>
</html>"""

    with pdf_path.open("wb") as pdf_file:
        status = pisa.CreatePDF(html, dest=pdf_file, encoding="utf-8")

    if status.err:
        raise RuntimeError(f"PDF generation failed with {status.err} error(s)")


if __name__ == "__main__":
    md_to_pdf(MD_PATH, PDF_PATH)
    print(f"PDF written to: {PDF_PATH}")
