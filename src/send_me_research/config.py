from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


DEFAULT_AUDIENCE_DESCRIPTION = (
    "ML related to LLMs, agents, robotics, and cyber/security, with extra emphasis on "
    "post-training, fine-tuning, self-improvement, tool use, code generation, code benchmarks, "
    "and methods that improve agentic task performance."
)
DEFAULT_PRIORITY_KEYWORDS = [
    "post-training",
    "fine-tuning",
    "self-distillation",
    "tool use",
    "code generation",
    "benchmark",
    "agentic tasks",
    "prompt injection",
    "robotics",
]
DEFAULT_ARXIV_CATEGORIES = [
    "cs.CL",
    "cs.AI",
    "cs.LG",
    "cs.CR",
    "cs.RO",
    "cs.CV",
    "cs.SE",
    "cs.MA",
    "cs.IR",
    "cs.HC",
    "stat.ML",
    "eess.SY",
    "eess.IV",
]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_csv(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def slugify(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return lowered or "default"


@dataclass(frozen=True)
class AudienceProfile:
    name: str
    recipients: list[str] = field(default_factory=list)
    description: str = DEFAULT_AUDIENCE_DESCRIPTION
    priority_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_PRIORITY_KEYWORDS))
    top_n: int = 15
    codex_shortlist_size: int = 80
    shortlist_core_size: int = 36
    shortlist_per_section: int = 12
    shortlist_per_profile: int = 10
    robotics_spotlight_count: int = 2
    codex_wildcard_candidates: int = 8
    enabled: bool = True

    @property
    def slug(self) -> str:
        return slugify(self.name)

    @classmethod
    def from_payload(cls, payload: dict[str, Any], defaults: "AppSettings") -> "AudienceProfile":
        recipients = payload.get("recipients", [])
        if isinstance(recipients, str):
            recipients = [item.strip() for item in recipients.split(",") if item.strip()]
        return cls(
            name=str(payload.get("name") or defaults.default_profile_name),
            recipients=[str(item).strip() for item in recipients if str(item).strip()],
            description=str(payload.get("description") or defaults.default_audience_description),
            priority_keywords=[
                str(item).strip()
                for item in payload.get("priority_keywords", defaults.default_priority_keywords)
                if str(item).strip()
            ],
            top_n=int(payload.get("top_n", defaults.top_n)),
            codex_shortlist_size=int(payload.get("codex_shortlist_size", defaults.codex_shortlist_size)),
            shortlist_core_size=int(payload.get("shortlist_core_size", defaults.shortlist_core_size)),
            shortlist_per_section=int(payload.get("shortlist_per_section", defaults.shortlist_per_section)),
            shortlist_per_profile=int(payload.get("shortlist_per_profile", defaults.shortlist_per_profile)),
            robotics_spotlight_count=int(payload.get("robotics_spotlight_count", defaults.robotics_spotlight_count)),
            codex_wildcard_candidates=int(payload.get("codex_wildcard_candidates", defaults.codex_wildcard_candidates)),
            enabled=coerce_bool(payload.get("enabled"), True),
        )


@dataclass
class AppSettings:
    workspace_root: Path
    timezone_name: str = "America/Los_Angeles"
    email_to: Optional[str] = None
    email_from: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 465
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    codex_bin: str = "codex"
    codex_model: str = "gpt-5.4"
    codex_reasoning_effort: str = "medium"
    codex_enable_search: bool = True
    codex_enable_wildcard_discovery: bool = True
    codex_wildcard_candidates: int = 8
    state_dir: Path = Path("state")
    output_dir: Path = Path("out")
    contact_email: Optional[str] = None
    profiles_path: Path = Path("digest_profiles.json")
    profiles_json: Optional[str] = None
    default_profile_name: str = "default"
    default_audience_description: str = DEFAULT_AUDIENCE_DESCRIPTION
    default_priority_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_PRIORITY_KEYWORDS))
    top_n: int = 15
    codex_shortlist_size: int = 80
    shortlist_core_size: int = 36
    shortlist_per_section: int = 12
    shortlist_per_profile: int = 10
    robotics_spotlight_count: int = 2
    robotics_min_heuristic_score: float = 2.5
    arxiv_max_results: int = 2000
    arxiv_categories: list[str] = field(default_factory=lambda: list(DEFAULT_ARXIV_CATEGORIES))
    openalex_per_page: int = 100
    openalex_max_pages: int = 2

    @classmethod
    def from_env(cls, workspace_root: str | Path | None = None) -> "AppSettings":
        root = Path(workspace_root or os.getcwd()).resolve()
        state_dir = Path(os.getenv("STATE_DIR", root / "state"))
        output_dir = Path(os.getenv("OUTPUT_DIR", root / "out"))
        profiles_path = Path(os.getenv("DIGEST_PROFILES_PATH", root / "digest_profiles.json"))
        smtp_port = int(os.getenv("SMTP_PORT", "465"))
        email_from = os.getenv("EMAIL_FROM") or os.getenv("SMTP_USERNAME")

        return cls(
            workspace_root=root,
            timezone_name=os.getenv("DIGEST_TIMEZONE", "America/Los_Angeles"),
            email_to=os.getenv("EMAIL_TO"),
            email_from=email_from,
            smtp_host=os.getenv("SMTP_HOST"),
            smtp_port=smtp_port,
            smtp_username=os.getenv("SMTP_USERNAME"),
            smtp_password=os.getenv("SMTP_PASSWORD"),
            codex_bin=os.getenv("CODEX_BIN", "codex"),
            codex_model=os.getenv("CODEX_MODEL", "gpt-5.4"),
            codex_reasoning_effort=os.getenv("CODEX_REASONING_EFFORT", "medium"),
            codex_enable_search=env_bool("CODEX_ENABLE_SEARCH", True),
            codex_enable_wildcard_discovery=env_bool("CODEX_ENABLE_WILDCARD_DISCOVERY", True),
            codex_wildcard_candidates=int(os.getenv("CODEX_WILDCARD_CANDIDATES", "8")),
            state_dir=state_dir,
            output_dir=output_dir,
            contact_email=os.getenv("OPENALEX_MAILTO"),
            profiles_path=profiles_path,
            profiles_json=os.getenv("DIGEST_PROFILES_JSON"),
            default_profile_name=os.getenv("DEFAULT_PROFILE_NAME", "default"),
            default_audience_description=os.getenv("DEFAULT_AUDIENCE_DESCRIPTION", DEFAULT_AUDIENCE_DESCRIPTION),
            default_priority_keywords=env_csv("DEFAULT_PRIORITY_KEYWORDS", DEFAULT_PRIORITY_KEYWORDS),
            top_n=int(os.getenv("TOP_N", "15")),
            codex_shortlist_size=int(os.getenv("CODEX_SHORTLIST_SIZE", "80")),
            shortlist_core_size=int(os.getenv("SHORTLIST_CORE_SIZE", "36")),
            shortlist_per_section=int(os.getenv("SHORTLIST_PER_SECTION", "12")),
            shortlist_per_profile=int(os.getenv("SHORTLIST_PER_PROFILE", "10")),
            robotics_spotlight_count=int(os.getenv("ROBOTICS_SPOTLIGHT_COUNT", "2")),
            robotics_min_heuristic_score=float(os.getenv("ROBOTICS_MIN_HEURISTIC_SCORE", "2.5")),
            arxiv_max_results=int(os.getenv("ARXIV_MAX_RESULTS", "2000")),
            arxiv_categories=env_csv("ARXIV_CATEGORIES", DEFAULT_ARXIV_CATEGORIES),
            openalex_per_page=int(os.getenv("OPENALEX_PER_PAGE", "100")),
            openalex_max_pages=int(os.getenv("OPENALEX_MAX_PAGES", "2")),
        )

    def ensure_directories(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def require_mail_settings(self) -> None:
        missing = [
            name
            for name, value in (
                ("SMTP_HOST", self.smtp_host),
                ("SMTP_USERNAME", self.smtp_username),
                ("SMTP_PASSWORD", self.smtp_password),
                ("EMAIL_FROM", self.email_from),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required mail settings: {', '.join(missing)}")

    def default_recipients(self) -> list[str]:
        return [item.strip() for item in (self.email_to or "").split(",") if item.strip()]

    def default_profile(self) -> AudienceProfile:
        return AudienceProfile(
            name=self.default_profile_name,
            recipients=self.default_recipients(),
            description=self.default_audience_description,
            priority_keywords=list(self.default_priority_keywords),
            top_n=self.top_n,
            codex_shortlist_size=self.codex_shortlist_size,
            shortlist_core_size=self.shortlist_core_size,
            shortlist_per_section=self.shortlist_per_section,
            shortlist_per_profile=self.shortlist_per_profile,
            robotics_spotlight_count=self.robotics_spotlight_count,
            codex_wildcard_candidates=self.codex_wildcard_candidates,
        )

    def has_explicit_profiles(self) -> bool:
        return self.profiles_path.exists() or bool(self.profiles_json)

    def load_profiles(self) -> list[AudienceProfile]:
        if self.profiles_path.exists():
            raw_text = self.profiles_path.read_text(encoding="utf-8")
        elif self.profiles_json:
            raw_text = self.profiles_json
        else:
            return [self.default_profile()]

        payload = json.loads(raw_text)
        raw_profiles = payload.get("profiles", payload) if isinstance(payload, dict) else payload
        profiles = [
            AudienceProfile.from_payload(item, self)
            for item in raw_profiles
            if isinstance(item, dict)
        ]
        enabled = [profile for profile in profiles if profile.enabled]
        return enabled or [self.default_profile()]

    def resolve_profiles(self, selected_name: str | None = None) -> list[AudienceProfile]:
        profiles = self.load_profiles()
        if not selected_name:
            return profiles
        selected_slug = slugify(selected_name)
        matches = [
            profile
            for profile in profiles
            if profile.slug == selected_slug or profile.name == selected_name
        ]
        if not matches:
            raise ValueError(f"Unknown digest profile: {selected_name}")
        return matches
