from __future__ import annotations

from pathlib import Path
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
        output_dir.mkdir(parents=True, exist_ok=True)
        return RenderedDigest(
            html=html,
            subject=payload.subject,
            digest_date=payload.digest_date,
            output_dir=str(output_dir),
        )

    def write(self, rendered: RenderedDigest) -> str:
        output_dir = Path(rendered.output_dir)
        html_path = output_dir / "digest.html"
        html_path.write_text(rendered.html, encoding="utf-8")
        return str(html_path)
