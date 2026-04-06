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
        profile_name="default",
        output_dir="out/digests/2026-03-30",
        entries=[make_entry()],
    )

    assert store.digest_already_sent("2026-03-30", "default")
    seen = store.load_seen_ids("default")
    assert "arxiv:1234.5678" in seen


def test_state_prunes_old_rows(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.record_send(
        digest_date="2026-03-30",
        subject="Older digest",
        profile_name="default",
        output_dir="out/digests/2026-03-30",
        entries=[make_entry()],
    )
    store.record_send(
        digest_date="2026-04-06",
        subject="Newer digest",
        profile_name="default",
        output_dir="out/digests/2026-04-06",
        entries=[make_entry()],
    )

    store.prune(retention_days=5, today=datetime(2026, 4, 6, tzinfo=timezone.utc).date())

    assert not store.digest_already_sent("2026-03-30", "default")
    assert store.digest_already_sent("2026-04-06", "default")


def test_state_isolated_by_profile(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.record_send(
        digest_date="2026-04-06",
        subject="Digest",
        profile_name="alice",
        output_dir="out/digests/2026-04-06/alice",
        entries=[make_entry()],
    )

    assert store.digest_already_sent("2026-04-06", "alice")
    assert not store.digest_already_sent("2026-04-06", "bob")
    assert store.load_seen_ids("alice")
    assert not store.load_seen_ids("bob")
