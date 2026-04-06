from datetime import date, datetime, timezone
from pathlib import Path

from send_me_research.models import DateWindow, DigestEntry, DigestPayload
from send_me_research.normalize import build_paper_record
from send_me_research.render import DigestRenderer, build_chatgpt_link, build_subject


def make_payload() -> DigestPayload:
    paper = build_paper_record(
        title="Agentic Security for LLM Workflows",
        abstract="We study prompt injection and defenses.",
        authors=["Alice", "Bob"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://example.com",
        pdf_url="https://example.com/paper.pdf",
        doi=None,
        source_ids=["arxiv:1111.2222"],
        extras=["cs.CL", "cs.CR"],
        canonical_id="arxiv:1111.2222",
    )
    entry = DigestEntry(
        paper=paper,
        section="Cyber",
        rank_score=8.9,
        why_it_matters="Directly relevant.",
        provenance="Example University and Example Labs; arXiv preprint.",
        signal_score=7.2,
        signal_rationale="Strong topic fit with credible authorship, but no external award signal yet.",
    )
    window = DateWindow(
        target_date=date(2026, 3, 30),
        timezone_name="America/Los_Angeles",
        start_at=datetime(2026, 3, 29, 0, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 3, 30, 23, 59, 59, tzinfo=timezone.utc),
    )
    return DigestPayload(
        digest_date=date(2026, 3, 30),
        window=window,
        subject=build_subject("2026-03-30", 1),
        entries=[entry],
        summary="One paper selected.",
    )


def test_render_writes_html_and_pdf(tmp_path: Path) -> None:
    template_dir = Path(__file__).resolve().parents[1] / "templates"
    renderer = DigestRenderer(template_dir)
    rendered = renderer.render(make_payload(), output_dir=tmp_path)
    html_path = renderer.write(rendered)

    html = Path(html_path).read_text(encoding="utf-8")

    assert "Agentic Security for LLM Workflows" in html
    assert "Origin &amp; Signal" in html
    assert "Example University and Example Labs; arXiv preprint." in html
    assert build_chatgpt_link("https://example.com") in html
