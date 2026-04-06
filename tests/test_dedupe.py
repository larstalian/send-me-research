from __future__ import annotations

from datetime import datetime, timezone

from send_me_research.dedupe import dedupe_records, filter_unseen
from send_me_research.normalize import build_paper_record


def paper(title: str, doi: str | None = None, source_id: str | None = None):
    return build_paper_record(
        title=title,
        abstract="Large language model security for agents.",
        authors=["A. Author"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="OpenAlex",
        landing_url="https://example.com/paper",
        pdf_url=None,
        doi=doi,
        source_ids=[source_id] if source_id else [],
        extras=["Computer science"],
        canonical_id=doi or source_id or title,
    )


def test_dedupe_prefers_single_entry_for_same_doi() -> None:
    a = paper("Prompt Injection Defenses", doi="10.1234/example")
    b = paper("Prompt Injection Defenses", doi="10.1234/example", source_id="arxiv:2501.12345")
    b.abstract = ""
    merged = dedupe_records([a, b])

    assert len(merged) == 1
    assert merged[0].doi == "10.1234/example"
    assert "arxiv:2501.12345" in merged[0].source_ids


def test_dedupe_fuzzy_title_match() -> None:
    a = paper("Autonomous Agent Security")
    b = paper("Autonomous Agent Security ")
    merged = dedupe_records([a, b])

    assert len(merged) == 1


def test_filter_unseen_blocks_known_ids() -> None:
    candidate = paper("Benchmarking Tool-Using LLMs", doi="10.9999/test")
    filtered = filter_unseen([candidate], {"10.9999/test"})

    assert filtered == []
