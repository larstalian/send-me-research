from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Sequence, Set

from .models import PaperRecord
from .normalize import title_hash, normalize_title


def merge_records(primary: PaperRecord, secondary: PaperRecord) -> PaperRecord:
    if not primary.abstract and secondary.abstract:
        primary.abstract = secondary.abstract
    if not primary.pdf_url and secondary.pdf_url:
        primary.pdf_url = secondary.pdf_url
    if not primary.doi and secondary.doi:
        primary.doi = secondary.doi
    if not primary.landing_url and secondary.landing_url:
        primary.landing_url = secondary.landing_url
    primary.source_ids = list(dict.fromkeys(primary.source_ids + secondary.source_ids))
    primary.topic_hints = list(dict.fromkeys(primary.topic_hints + secondary.topic_hints))
    primary.profile_hints = list(dict.fromkeys(primary.profile_hints + secondary.profile_hints))
    primary.authors = primary.authors or secondary.authors
    primary.heuristic_score = max(primary.heuristic_score, secondary.heuristic_score)
    primary.profile_score = max(primary.profile_score, secondary.profile_score)
    primary.screening_score = max(primary.screening_score, secondary.screening_score)
    return primary


def dedupe_records(records: Sequence[PaperRecord]) -> List[PaperRecord]:
    by_key: Dict[str, PaperRecord] = {}
    deduped: List[PaperRecord] = []

    for record in sorted(records, key=lambda item: item.heuristic_score, reverse=True):
        keys = [
            record.doi.lower() if record.doi else "",
            next((sid for sid in record.source_ids if "arxiv" in sid.lower() or "." in sid), ""),
            title_hash(record.title),
        ]
        keys = [key for key in keys if key]
        found = None
        for key in keys:
            if key in by_key:
                found = by_key[key]
                break
        if found:
            merge_records(found, record)
            continue

        normalized_new = normalize_title(record.title)
        fuzzy_match = next(
            (
                existing
                for existing in deduped
                if SequenceMatcher(None, normalize_title(existing.title), normalized_new).ratio() >= 0.97
            ),
            None,
        )
        if fuzzy_match:
            merge_records(fuzzy_match, record)
            continue

        deduped.append(record)
        for key in keys:
            by_key[key] = record

    return deduped


def filter_unseen(records: Iterable[PaperRecord], seen_ids: Set[str]) -> List[PaperRecord]:
    output = []
    for record in records:
        identifiers = {record.canonical_id, title_hash(record.title)}
        if record.doi:
            identifiers.add(record.doi.lower())
        identifiers.update(record.source_ids)
        if identifiers & seen_ids:
            continue
        output.append(record)
    return output
