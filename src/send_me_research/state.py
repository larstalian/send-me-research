from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
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

    def load_seen_ids(self) -> Set[str]:
        seen: Set[str] = set()
        for row in self._read_jsonl(self.papers_seen_path):
            for key in row.get("identifiers", []):
                seen.add(str(key))
        return seen

    def digest_already_sent(self, digest_date: str) -> bool:
        return any(row.get("digest_date") == digest_date for row in self._read_jsonl(self.digests_sent_path))

    def record_send(
        self,
        *,
        digest_date: str,
        subject: str,
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
                    "digest_date": digest_date,
                    "title": entry.paper.title,
                    "identifiers": list(dict.fromkeys([identifier for identifier in identifiers if identifier])),
                },
            )

        self._append_jsonl(
            self.digests_sent_path,
            {
                "sent_at": datetime.utcnow().isoformat() + "Z",
                "digest_date": digest_date,
                "subject": subject,
                "output_dir": f"out/digests/{digest_date}",
                "paper_ids": [entry.paper.canonical_id for entry in entries],
            },
        )

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
