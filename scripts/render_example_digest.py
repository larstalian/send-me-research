#!/usr/bin/env python3
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from send_me_research.models import DateWindow, DigestEntry, DigestPayload
from send_me_research.normalize import build_paper_record
from send_me_research.render import DigestRenderer, build_subject


def make_entry(
    *,
    title: str,
    abstract: str,
    authors: list[str],
    published_at: datetime,
    source: str,
    landing_url: str,
    section: str,
    rank_score: float,
    why_it_matters: str,
    provenance: str,
    signal_score: float,
    signal_rationale: str,
    canonical_id: str,
    extras: list[str],
) -> DigestEntry:
    paper = build_paper_record(
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=published_at,
        source=source,
        landing_url=landing_url,
        pdf_url=None,
        doi=None,
        source_ids=[canonical_id],
        extras=extras,
        canonical_id=canonical_id,
    )
    return DigestEntry(
        paper=paper,
        section=section,
        rank_score=rank_score,
        why_it_matters=why_it_matters,
        provenance=provenance,
        signal_score=signal_score,
        signal_rationale=signal_rationale,
    )


def build_payload() -> DigestPayload:
    entries = [
        make_entry(
            title="Embarrassingly Simple Self-Distillation Improves Code Generation",
            abstract=(
                "A minimal post-training recipe improves pass@1 on code-generation benchmarks "
                "without requiring a verifier, reward model, or reinforcement learning."
            ),
            authors=["Ruixiang Zhang", "Yifan Song", "Apple"],
            published_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            source="arXiv",
            landing_url="https://arxiv.org/abs/2604.01193",
            section="LLMs",
            rank_score=9.8,
            why_it_matters=(
                "A simple post-training method that lifts coding performance is exactly the kind "
                "of high-leverage paper people can try quickly in real agentic systems."
            ),
            provenance="Apple-authored arXiv preprint with linked project code.",
            signal_score=7.4,
            signal_rationale="Credible industrial authorship and clear practical relevance, but still a fresh preprint.",
            canonical_id="arxiv:2604.01193",
            extras=["cs.CL", "code generation", "post-training"],
        ),
        make_entry(
            title="AudioHijack: Context-Agnostic Auditory Prompt Injection Against Large Audio-Language Models",
            abstract=(
                "We study prompt injection in multimodal audio-language systems and evaluate how "
                "adversarial auditory prompts transfer across model families and target behaviors."
            ),
            authors=["Meng Chen", "ZJU MUSLAB"],
            published_at=datetime(2026, 3, 30, tzinfo=timezone.utc),
            source="arXiv",
            landing_url="https://arxiv.org/abs/2603.99999",
            section="Cyber",
            rank_score=9.1,
            why_it_matters=(
                "Multimodal prompt injection research is becoming directly relevant to real voice "
                "and agent interfaces, so strong evaluations here matter a lot."
            ),
            provenance="Academic preprint with reproducibility-focused artifact release.",
            signal_score=6.8,
            signal_rationale="Strong security relevance and artifact support, though venue outcome is not yet known.",
            canonical_id="arxiv:2603.99999",
            extras=["cs.CR", "prompt injection", "audio"],
        ),
        make_entry(
            title="Embodied Planning with Vision-Language-Action Models in Cluttered Homes",
            abstract=(
                "A vision-language-action system improves manipulation planning in cluttered home "
                "environments through grounded subgoal generation and sim-to-real transfer."
            ),
            authors=["Jordan Lee", "Mina Park", "Robotics Lab"],
            published_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
            source="OpenAlex",
            landing_url="https://example.com/robotics-paper",
            section="Robotics",
            rank_score=8.7,
            why_it_matters=(
                "It is a good example of robotics work that earns a spot in the digest because it "
                "connects foundation-model planning to real-world control."
            ),
            provenance="University robotics lab preprint with sim-to-real experiments.",
            signal_score=6.5,
            signal_rationale="Solid embodied-AI fit and real-world evaluation, but limited external prestige signal.",
            canonical_id="openalex:robotics-demo",
            extras=["cs.RO", "robotics", "vision-language-action"],
        ),
    ]

    window = DateWindow(
        target_date=date(2026, 4, 7),
        timezone_name="America/Los_Angeles",
        start_at=datetime(2026, 4, 6, 0, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 7, 23, 59, 59, tzinfo=timezone.utc),
    )
    return DigestPayload(
        digest_date=date(2026, 4, 7),
        window=window,
        subject=build_subject("2026-04-07", len(entries)),
        entries=entries,
        summary="Three papers selected across LLMs, Cyber, and Robotics.",
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = repo_root / "examples" / "digest-example"
    renderer = DigestRenderer(repo_root / "templates")
    rendered = renderer.render(build_payload(), output_dir=output_dir)
    html_path = renderer.write(rendered)
    print(html_path)


if __name__ == "__main__":
    main()
