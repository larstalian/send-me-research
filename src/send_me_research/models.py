from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


@dataclass
class PaperRecord:
    canonical_id: str
    title: str
    abstract: str
    authors: List[str]
    published_at: datetime
    source: str
    landing_url: str
    pdf_url: Optional[str] = None
    doi: Optional[str] = None
    source_ids: List[str] = field(default_factory=list)
    topic_hints: List[str] = field(default_factory=list)
    heuristic_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["published_at"] = self.published_at.isoformat()
        return payload


@dataclass
class DigestEntry:
    paper: PaperRecord
    section: str
    rank_score: float
    why_it_matters: str
    provenance: str = ""
    signal_score: float = 0.0
    signal_rationale: str = ""
    keep: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper": self.paper.to_dict(),
            "section": self.section,
            "rank_score": self.rank_score,
            "why_it_matters": self.why_it_matters,
            "provenance": self.provenance,
            "signal_score": self.signal_score,
            "signal_rationale": self.signal_rationale,
            "keep": self.keep,
        }


@dataclass
class DateWindow:
    target_date: date
    timezone_name: str
    start_at: datetime
    end_at: datetime

    def label(self) -> str:
        return f"{self.start_at.date().isoformat()} to {self.end_at.date().isoformat()} ({self.timezone_name})"


@dataclass
class DigestPayload:
    digest_date: date
    window: DateWindow
    subject: str
    entries: List[DigestEntry]
    summary: str


@dataclass
class RenderedDigest:
    html: str
    pdf_bytes: bytes
    subject: str
    digest_date: date
    output_dir: str


@dataclass
class DigestRunResult:
    digest_date: date
    entries: List[DigestEntry]
    output_dir: str
    html_path: str
    pdf_path: str
    subject: str
    skipped_send: bool = False
