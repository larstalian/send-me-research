from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    top_n: int = 15
    codex_shortlist_size: int = 25
    robotics_spotlight_count: int = 2
    robotics_min_heuristic_score: float = 2.5
    arxiv_max_results: int = 250
    openalex_per_page: int = 100
    openalex_max_pages: int = 2

    @classmethod
    def from_env(cls, workspace_root: str | Path | None = None) -> "AppSettings":
        root = Path(workspace_root or os.getcwd()).resolve()
        state_dir = Path(os.getenv("STATE_DIR", root / "state"))
        output_dir = Path(os.getenv("OUTPUT_DIR", root / "out"))
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
            top_n=int(os.getenv("TOP_N", "15")),
            codex_shortlist_size=int(os.getenv("CODEX_SHORTLIST_SIZE", "25")),
            robotics_spotlight_count=int(os.getenv("ROBOTICS_SPOTLIGHT_COUNT", "2")),
            robotics_min_heuristic_score=float(os.getenv("ROBOTICS_MIN_HEURISTIC_SCORE", "2.5")),
            arxiv_max_results=int(os.getenv("ARXIV_MAX_RESULTS", "250")),
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
                ("EMAIL_TO", self.email_to),
                ("SMTP_HOST", self.smtp_host),
                ("SMTP_USERNAME", self.smtp_username),
                ("SMTP_PASSWORD", self.smtp_password),
                ("EMAIL_FROM", self.email_from),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required mail settings: {', '.join(missing)}")
