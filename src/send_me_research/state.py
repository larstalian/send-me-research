from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Set

from .models import DigestEntry
from .normalize import title_hash


@dataclass
class StateStore:
    state_dir: Path

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.papers_seen_path = self.state_dir / "papers_seen.jsonl"
        self.digests_sent_path = self.state_dir / "digests_sent.jsonl"
        for path in (self.papers_seen_path, self.digests_sent_path):
            path.touch(exist_ok=True)

    def load_seen_ids(self, profile_name: str = "default") -> Set[str]:
        seen: Set[str] = set()
        for row in self._read_jsonl(self.papers_seen_path):
            if self._row_profile(row) != profile_name:
                continue
            for key in row.get("identifiers", []):
                seen.add(str(key))
        return seen

    def digest_already_sent(self, digest_date: str, profile_name: str = "default") -> bool:
        return any(
            row.get("digest_date") == digest_date and self._row_profile(row) == profile_name
            for row in self._read_jsonl(self.digests_sent_path)
        )

    def record_send(
        self,
        *,
        digest_date: str,
        subject: str,
        profile_name: str,
        output_dir: str,
        entries: Iterable[DigestEntry],
    ) -> None:
        entries = list(entries)
        for entry in entries:
            identifiers = [entry.paper.canonical_id, title_hash(entry.paper.title)]
            if entry.paper.doi:
                identifiers.append(entry.paper.doi.lower())
            identifiers.extend(entry.paper.source_ids)
            self._append_jsonl(
                self.papers_seen_path,
                {
                    "sent_at": datetime.utcnow().isoformat() + "Z",
                    "profile": profile_name,
                    "digest_date": digest_date,
                    "title": entry.paper.title,
                    "identifiers": list(dict.fromkeys([identifier for identifier in identifiers if identifier])),
                },
            )

        self._append_jsonl(
            self.digests_sent_path,
            {
                "sent_at": datetime.utcnow().isoformat() + "Z",
                "profile": profile_name,
                "digest_date": digest_date,
                "subject": subject,
                "output_dir": output_dir,
                "paper_ids": [entry.paper.canonical_id for entry in entries],
            },
        )

    def prune(self, *, retention_days: int, today: date | None = None) -> None:
        today = today or datetime.utcnow().date()
        cutoff = today - timedelta(days=max(retention_days, 0))
        papers = [
            row
            for row in self._read_jsonl(self.papers_seen_path)
            if self._row_digest_date(row) >= cutoff
        ]
        digests = [
            row
            for row in self._read_jsonl(self.digests_sent_path)
            if self._row_digest_date(row) >= cutoff
        ]
        self._write_jsonl(self.papers_seen_path, papers)
        self._write_jsonl(self.digests_sent_path, digests)

    def _read_jsonl(self, path: Path) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        if not path.exists():
            return rows
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
        return rows

    def _append_jsonl(self, path: Path, payload: Dict[str, object]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            handle.write("\n")

    def _write_jsonl(self, path: Path, rows: Iterable[Dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True))
                handle.write("\n")

    def _row_digest_date(self, row: Dict[str, object]) -> date:
        raw = row.get("digest_date")
        if isinstance(raw, str):
            return date.fromisoformat(raw)
        raise ValueError(f"State row is missing digest_date: {row}")

    def _row_profile(self, row: Dict[str, object]) -> str:
        raw = row.get("profile")
        if isinstance(raw, str) and raw.strip():
            return raw
        return "default"
