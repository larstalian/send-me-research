from datetime import date

from send_me_research.normalize import build_window, guess_topic_hints, reconstruct_openalex_abstract, section_from_hints


def test_build_window_spans_yesterday_and_today() -> None:
    window = build_window(date(2026, 3, 30), "America/Los_Angeles")

    assert window.start_at.isoformat() == "2026-03-29T00:00:00-07:00"
    assert window.end_at.isoformat() == "2026-03-30T23:59:59-07:00"


def test_reconstruct_openalex_abstract() -> None:
    abstract = reconstruct_openalex_abstract({"Hello": [0], "world": [1], "again": [2]})
    assert abstract == "Hello world again"


def test_guess_topic_hints_detects_multiple_sections() -> None:
    hints = guess_topic_hints(
        "Agentic red teaming for large language models",
        "We study prompt injection, multi-agent defense, and LLM evaluation.",
    )
    assert "LLMs" in hints
    assert "Agents" in hints
    assert "Cyber" in hints


def test_guess_topic_hints_detects_robotics() -> None:
    hints = guess_topic_hints(
        "Vision-Language-Action Policies for Robot Manipulation",
        "We study embodied robot learning and sim2real transfer for grasping tasks.",
        extras=["cs.RO"],
    )

    assert "Robotics" in hints
    assert section_from_hints(hints) == "Robotics"
