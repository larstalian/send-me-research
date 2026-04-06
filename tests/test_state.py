from pathlib import Path

from send_me_research.models import DigestEntry
from send_me_research.normalize import build_paper_record
from send_me_research.state import StateStore
from datetime import datetime, timezone


def make_entry() -> DigestEntry:
    paper = build_paper_record(
        title="A daily paper",
        abstract="Abstract",
        authors=["Author One"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://example.com",
        pdf_url=None,
        doi=None,
        source_ids=["arxiv:1234.5678"],
        extras=["cs.CL"],
        canonical_id="arxiv:1234.5678",
    )
    return DigestEntry(paper=paper, section="LLMs", rank_score=9.0, why_it_matters="Useful.")


def test_state_records_sent_digest(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.record_send(
        digest_date="2026-03-30",
        subject="Digest",
        output_dir=str(tmp_path / "out"),
        entries=[make_entry()],
    )

    assert store.digest_already_sent("2026-03-30")
    seen = store.load_seen_ids()
    assert "arxiv:1234.5678" in seen
