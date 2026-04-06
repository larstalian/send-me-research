import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from send_me_research.config import AppSettings
from send_me_research.codex_rank import CodexRanker
from send_me_research.normalize import build_paper_record


def fake_runner(args, **kwargs):
    if args[1:3] == ["login", "status"]:
        return subprocess.CompletedProcess(args, 0, stdout="Logged in using ChatGPT", stderr="")

    output_path = Path(args[args.index("-o") + 1])
    assert "--search" in args
    input_text = kwargs.get("input", "")
    if "Existing candidates to avoid duplicating:" in input_text:
        payload = {
            "summary": "Discovered one extra paper.",
            "discoveries": [
                {
                    "title": "Prompt Injection Red Teaming for Agents",
                    "abstract": "A newly discovered agent security paper.",
                    "authors": ["Researcher"],
                    "published_at": "2026-03-30",
                    "source": "CodexDiscovery",
                    "landing_url": "https://example.com/discovered-paper",
                    "pdf_url": "",
                    "doi": "",
                    "interest_score": 8.7,
                    "why_discovered": "Strong match for the digest topics.",
                }
            ],
        }
    elif "You are enriching selected daily-digest papers with provenance context." in input_text:
        payload = {
            "summary": "Enriched one entry.",
            "entries": [
                {
                    "canonical_id": "arxiv:9999.0001",
                    "provenance": "Example Lab at Example University; arXiv preprint.",
                    "signal_score": 7.8,
                    "signal_rationale": "Clear institutional provenance, but no venue or award signal yet.",
                }
            ],
        }
    else:
        payload = {
            "summary": "Selected one entry.",
            "entries": [
                {
                    "canonical_id": "arxiv:9999.0001",
                    "section": "LLMs",
                    "rank_score": 9.4,
                    "why_it_matters": "Strong fit for the digest.",
                    "provenance": "",
                    "signal_score": 0.0,
                    "signal_rationale": "",
                    "keep": True,
                }
            ],
        }
    output_path.write_text(json.dumps(payload), encoding="utf-8")
    return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_codex_ranker_uses_schema_output() -> None:
    record = build_paper_record(
        title="Large Language Model Agents",
        abstract="An agentic systems paper.",
        authors=["Author"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://example.com",
        pdf_url=None,
        doi=None,
        source_ids=["arxiv:9999.0001"],
        extras=["cs.AI"],
        canonical_id="arxiv:9999.0001",
    )
    ranker = CodexRanker(runner=fake_runner)
    profile = AppSettings.from_env(Path(__file__).resolve().parents[1]).default_profile()

    entries = ranker.rank(
        candidates=[record],
        target_date=date(2026, 3, 30),
        timezone_name="America/Los_Angeles",
        top_n=15,
        audience_profile=profile,
    )

    assert len(entries) == 1
    assert entries[0].paper.canonical_id == "arxiv:9999.0001"
    assert entries[0].section == "LLMs"
    assert entries[0].provenance == "Example Lab at Example University; arXiv preprint."
    assert entries[0].signal_score == 7.8
    assert "profile_hints" in ranker._build_prompt(
        [record],
        target_date=date(2026, 3, 30),
        timezone_name="America/Los_Angeles",
        top_n=15,
        audience_profile=profile,
    )


def test_codex_auth_check() -> None:
    ranker = CodexRanker(runner=fake_runner)
    assert "Logged in using ChatGPT" in ranker.auth_check()


def test_codex_wildcard_discovery_returns_records() -> None:
    existing = build_paper_record(
        title="Existing Agent Paper",
        abstract="Existing shortlist item.",
        authors=["Author"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://example.com/existing",
        pdf_url=None,
        doi=None,
        source_ids=["arxiv:existing"],
        extras=["cs.AI"],
        canonical_id="arxiv:existing",
    )
    ranker = CodexRanker(runner=fake_runner)
    profile = AppSettings.from_env(Path(__file__).resolve().parents[1]).default_profile()

    discoveries = ranker.discover_wildcards(
        target_date=date(2026, 3, 30),
        timezone_name="America/Los_Angeles",
        max_candidates=5,
        existing_candidates=[existing],
        audience_profile=profile,
    )

    assert len(discoveries) == 1
    assert discoveries[0].landing_url == "https://example.com/discovered-paper"
    assert discoveries[0].heuristic_score >= 8.7
