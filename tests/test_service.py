from datetime import date, datetime, timezone
from pathlib import Path

from send_me_research.config import AppSettings
from send_me_research.models import DigestEntry
from send_me_research.normalize import build_paper_record
from send_me_research.service import DigestService


class FakeSourceClient:
    def fetch_arxiv(self, window, max_results=250):
        return [
            build_paper_record(
                title="Agentic Security for LLM Systems",
                abstract="Prompt injection defense for LLM agents.",
                authors=["Alice"],
                published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
                source="arXiv",
                landing_url="https://arxiv.org/abs/2503.00001",
                pdf_url="https://arxiv.org/pdf/2503.00001.pdf",
                doi=None,
                source_ids=["arxiv:2503.00001"],
                extras=["cs.CL", "cs.CR"],
                canonical_id="arxiv:2503.00001",
            )
        ]

    def fetch_openalex(self, window, per_page=100, max_pages=2):
        return []

    def enrich_with_crossref(self, record):
        return record

    def close(self):
        return None


class FakeRanker:
    def __init__(self):
        self.last_rank_candidates = []

    def auth_check(self):
        return "Logged in using ChatGPT"

    def discover_wildcards(self, *, target_date, timezone_name, max_candidates, existing_candidates, audience_profile):
        return [
            build_paper_record(
                title="Discovered Cyber Paper",
                abstract="A web-discovered prompt injection paper.",
                authors=["Bob"],
                published_at=datetime(2026, 3, 29, tzinfo=timezone.utc),
                source="CodexDiscovery",
                landing_url="https://example.com/discovered",
                pdf_url=None,
                doi=None,
                source_ids=["https://example.com/discovered"],
                extras=["prompt injection", "cybersecurity"],
                canonical_id="https://example.com/discovered",
            )
        ]

    def rank(self, *, candidates, target_date, timezone_name, top_n, audience_profile):
        self.last_rank_candidates = candidates
        return [
            DigestEntry(
                paper=candidates[0],
                section="Cyber",
                rank_score=9.5,
                why_it_matters="Direct fit for the digest.",
            )
        ]


def test_preview_digest_writes_artifacts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings = AppSettings.from_env(repo_root)
    settings.state_dir = tmp_path / "state"
    settings.output_dir = tmp_path / "out"
    service = DigestService(settings)
    service.source_client = FakeSourceClient()
    fake_ranker = FakeRanker()
    service.rank = fake_ranker

    result = service.preview_digest(target_date=date(2026, 3, 30))

    assert Path(result.html_path).exists()
    manifest = Path(result.output_dir) / "manifest.json"
    assert manifest.exists()
    assert len(result.entries) == 1
    assert any(candidate.canonical_id == "https://example.com/discovered" for candidate in fake_ranker.last_rank_candidates)


def test_build_shortlist_keeps_robotics_spotlight(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings = AppSettings.from_env(repo_root)
    settings.state_dir = tmp_path / "state"
    settings.output_dir = tmp_path / "out"
    settings.codex_shortlist_size = 1
    settings.robotics_spotlight_count = 1
    service = DigestService(settings)

    llm_paper = build_paper_record(
        title="Foundation Models for Agents",
        abstract="Large language model agents with planning.",
        authors=["Alice"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://example.com/llm",
        pdf_url=None,
        doi=None,
        source_ids=["llm"],
        extras=["cs.AI"],
        canonical_id="llm",
    )
    robotics_paper = build_paper_record(
        title="Embodied Robot Learning with Vision-Language-Action Policies",
        abstract="A robotics paper about embodied manipulation and sim2real transfer.",
        authors=["Bob"],
        published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://example.com/robotics",
        pdf_url=None,
        doi=None,
        source_ids=["robotics"],
        extras=["cs.RO"],
        canonical_id="robotics",
    )

    shortlist = service.build_shortlist([llm_paper, robotics_paper], settings.default_profile())

    assert len(shortlist) == 2
    assert any(paper.canonical_id == "robotics" for paper in shortlist)


def test_build_shortlist_rescues_profile_fit_paper(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings = AppSettings.from_env(repo_root)
    settings.state_dir = tmp_path / "state"
    settings.output_dir = tmp_path / "out"
    settings.codex_shortlist_size = 8
    settings.shortlist_core_size = 2
    settings.shortlist_per_section = 0
    settings.shortlist_per_profile = 2
    settings.robotics_spotlight_count = 0
    service = DigestService(settings)

    noisy_topical = []
    for index in range(6):
        noisy_topical.append(
            build_paper_record(
                title=f"Agentic Security Paper {index}",
                abstract="LLM agent prompt injection security benchmark with robots and workflows.",
                authors=["Author"],
                published_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                source="OpenAlex",
                landing_url=f"https://example.com/noisy-{index}",
                pdf_url=None,
                doi=None,
                source_ids=[f"noisy-{index}"],
                extras=["cs.AI", "cs.CR"],
                canonical_id=f"noisy-{index}",
            )
        )

    target = build_paper_record(
        title="Embarrassingly Simple Self-Distillation Improves Code Generation",
        abstract="A post-training method for LLM code generation that improves LiveCodeBench performance without a verifier or RL.",
        authors=["Ruixiang Zhang"],
        published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://arxiv.org/abs/2604.01193",
        pdf_url=None,
        doi=None,
        source_ids=["2604.01193v1"],
        extras=["cs.CL"],
        canonical_id="2604.01193v1",
    )

    shortlist = service.build_shortlist(noisy_topical + [target], settings.default_profile())

    assert any(paper.canonical_id == "2604.01193v1" for paper in shortlist)


def test_rank_entries_caps_low_confidence_archive_releases(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    settings = AppSettings.from_env(repo_root)
    settings.state_dir = tmp_path / "state"
    settings.output_dir = tmp_path / "out"
    service = DigestService(settings)

    strong = build_paper_record(
        title="Serious Post-Training Paper",
        abstract="A strong fine-tuning and code generation paper from a known lab.",
        authors=["Known Author"],
        published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        source="arXiv",
        landing_url="https://arxiv.org/abs/2604.12345",
        pdf_url=None,
        doi=None,
        source_ids=["strong"],
        extras=["cs.CL"],
        canonical_id="strong",
    )
    weak_archive_one = build_paper_record(
        title="Unknown Zenodo Release One",
        abstract="A topical but weakly validated code generation release.",
        authors=["Unknown"],
        published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        source="OpenAlex",
        landing_url="https://doi.org/10.5281/zenodo.11111111",
        pdf_url=None,
        doi="https://doi.org/10.5281/zenodo.11111111",
        source_ids=["weak-1"],
        extras=["cs.CL"],
        canonical_id="weak-1",
    )
    weak_archive_two = build_paper_record(
        title="Unknown Zenodo Release Two",
        abstract="Another topical but weakly validated code generation release.",
        authors=["Unknown"],
        published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
        source="OpenAlex",
        landing_url="https://doi.org/10.5281/zenodo.22222222",
        pdf_url=None,
        doi="https://doi.org/10.5281/zenodo.22222222",
        source_ids=["weak-2"],
        extras=["cs.CL"],
        canonical_id="weak-2",
    )

    class Ranker:
        def rank(self, *, candidates, target_date, timezone_name, top_n, audience_profile):
            return [
                DigestEntry(
                    paper=weak_archive_one,
                    section="LLMs",
                    rank_score=92.0,
                    why_it_matters="Topical but weakly validated.",
                    provenance="This appears to be a Zenodo self-published release by an unknown author, and I did not verify an institutional affiliation or peer-reviewed venue for it.",
                    signal_score=2.0,
                    signal_rationale="The provenance signal is limited to archival hosting on Zenodo without stronger external confirmation.",
                ),
                DigestEntry(
                    paper=strong,
                    section="LLMs",
                    rank_score=89.0,
                    why_it_matters="Strong and well grounded.",
                    provenance="Known lab authorship with clear institutional footprint.",
                    signal_score=7.0,
                    signal_rationale="Clear identifiable authorship and stronger external signal.",
                ),
                DigestEntry(
                    paper=weak_archive_two,
                    section="LLMs",
                    rank_score=88.0,
                    why_it_matters="Also topical but weakly validated.",
                    provenance="This appears to be a Zenodo self-published release by an unknown author, and I did not verify an institutional affiliation or peer-reviewed venue for it.",
                    signal_score=1.0,
                    signal_rationale="Only archival hosting on Zenodo was found.",
                ),
            ]

    service.rank = Ranker()

    entries = service.rank_entries(
        [strong, weak_archive_one, weak_archive_two],
        target_date=date(2026, 4, 20),
        profile=settings.default_profile(),
    )

    assert entries[0].paper.canonical_id == "strong"
    kept_ids = [entry.paper.canonical_id for entry in entries]
    assert kept_ids.count("weak-1") + kept_ids.count("weak-2") == 1
