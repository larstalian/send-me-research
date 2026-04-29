import json
from pathlib import Path

from send_me_research.config import AppSettings


def test_load_profiles_from_json(tmp_path: Path) -> None:
    profiles_path = tmp_path / "digest_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "name": "Applied ML",
                        "recipients": ["ml@example.com"],
                        "description": "LLMs and agents",
                        "priority_keywords": ["fine-tuning", "code generation"],
                        "top_n": 12,
                    },
                    {
                        "name": "Security Team",
                        "recipients": ["security@example.com"],
                        "description": "Cyber and robotics",
                        "priority_keywords": ["prompt injection", "robot learning"],
                        "top_n": 8,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    settings = AppSettings.from_env(tmp_path)
    settings.profiles_path = profiles_path

    profiles = settings.load_profiles()

    assert [profile.name for profile in profiles] == ["Applied ML", "Security Team"]
    assert profiles[0].top_n == 12
    assert profiles[1].recipients == ["security@example.com"]


def test_load_profiles_from_env_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(
        "DIGEST_PROFILES_JSON",
        json.dumps(
            [
                {
                    "name": "Agents",
                    "recipients": ["agents@example.com"],
                    "description": "Agent systems",
                    "priority_keywords": ["tool use"],
                }
            ]
        ),
    )

    settings = AppSettings.from_env(tmp_path)
    profiles = settings.load_profiles()

    assert [profile.name for profile in profiles] == ["Agents"]
    assert profiles[0].recipients == ["agents@example.com"]


def test_default_profile_fallback_uses_env_email(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EMAIL_TO", "one@example.com,two@example.com")
    settings = AppSettings.from_env(tmp_path)

    profile = settings.default_profile()

    assert profile.recipients == ["one@example.com", "two@example.com"]
    assert "post-training" in profile.description


def test_arxiv_categories_can_be_configured_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARXIV_CATEGORIES", "cs.CL, stat.ML")
    settings = AppSettings.from_env(tmp_path)

    assert settings.arxiv_categories == ["cs.CL", "stat.ML"]
