from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import DigestPayload, RenderedDigest


def build_subject(digest_date: str, count: int) -> str:
    return f"Daily Research Digest - {digest_date} ({count} papers)"


def build_chatgpt_link(paper_url: str) -> str:
    prompt = f"Read this paper and give me 5 bullet takeaways, main novelty, and weaknesses: {paper_url}"
    return f"https://chatgpt.com/?q={quote(prompt, safe='')}"


class DigestRenderer:
    def __init__(self, template_dir: Path) -> None:
        self.template_dir = template_dir
        self.environment = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, payload: DigestPayload, output_dir: Path) -> RenderedDigest:
        template = self.environment.get_template("digest.html.j2")
        entries = []
        for entry in payload.entries:
            item = entry.to_dict()
            item["chatgpt_url"] = build_chatgpt_link(entry.paper.landing_url)
            entries.append(item)
        html = template.render(
            digest_date=payload.digest_date.isoformat(),
            window_label=payload.window.label(),
            entries=entries,
            summary=payload.summary,
            total=len(payload.entries),
        )
        pdf_bytes = self._render_pdf(html)
        output_dir.mkdir(parents=True, exist_ok=True)
        return RenderedDigest(
            html=html,
            pdf_bytes=pdf_bytes,
            subject=payload.subject,
            digest_date=payload.digest_date,
            output_dir=str(output_dir),
        )

    def write(self, rendered: RenderedDigest) -> tuple[str, str]:
        output_dir = Path(rendered.output_dir)
        html_path = output_dir / "digest.html"
        pdf_path = output_dir / "digest.pdf"
        html_path.write_text(rendered.html, encoding="utf-8")
        pdf_path.write_bytes(rendered.pdf_bytes)
        return str(html_path), str(pdf_path)

    def _render_pdf(self, html: str) -> bytes:
        try:
            from weasyprint import HTML

            return HTML(string=html).write_pdf()
        except Exception:
            return _fallback_pdf(html)


def _fallback_pdf(html: str) -> bytes:
    text = html.replace("(", "[").replace(")", "]")
    text = text.replace("\n", " ")
    text = text[:1500]
    content = f"BT /F1 10 Tf 40 750 Td ({text}) Tj ET"
    body = [
        "%PDF-1.4",
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
        f"4 0 obj << /Length {len(content)} >> stream\n{content}\nendstream endobj",
        "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        "xref",
        "0 6",
        "0000000000 65535 f ",
        "0000000010 00000 n ",
        "0000000063 00000 n ",
        "0000000122 00000 n ",
        "0000000265 00000 n ",
        "0000000380 00000 n ",
        "trailer << /Size 6 /Root 1 0 R >>",
        "startxref",
        "450",
        "%%EOF",
    ]
    return "\n".join(body).encode("utf-8")
