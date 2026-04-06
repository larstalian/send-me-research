from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

from .codex_rank import CodexAuthError, CodexRanker
from .config import AppSettings
from .dedupe import dedupe_records, filter_unseen
from .mail import Mailer
from .models import DigestEntry, DigestPayload, DigestRunResult, PaperRecord
from .normalize import PROFILE_ORDER, SECTION_ORDER, build_window, section_sort_key
from .render import DigestRenderer, build_subject
from .sources import SourceClient
from .state import StateStore


class DigestService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.settings.ensure_directories()
        self.state = StateStore(self.settings.state_dir)
        self.rank = CodexRanker(
            codex_bin=self.settings.codex_bin,
            model=self.settings.codex_model,
            reasoning_effort=self.settings.codex_reasoning_effort,
            enable_search=self.settings.codex_enable_search,
        )
        self.renderer = DigestRenderer(self.settings.workspace_root / "templates")
        self.source_client = SourceClient(contact_email=self.settings.contact_email)

    def close(self) -> None:
        self.source_client.close()

    def auth_check(self) -> str:
        return self.rank.auth_check()

    def run_digest(self, *, target_date: date, send: bool) -> DigestRunResult:
        window = build_window(target_date, self.settings.timezone_name)
        digest_date = target_date.isoformat()
        if send and self.state.digest_already_sent(digest_date):
            output_dir = self._output_dir_for_date(target_date)
            return DigestRunResult(
                digest_date=target_date,
                entries=[],
                output_dir=str(output_dir),
                html_path=str(output_dir / "digest.html"),
                pdf_path=str(output_dir / "digest.pdf"),
                subject=build_subject(digest_date, 0),
                skipped_send=True,
            )

        candidates = self.collect_candidates(window)
        candidates = self.augment_candidates_with_codex_discoveries(window=window, target_date=target_date, candidates=candidates)
        seen_ids = self.state.load_seen_ids()
        unseen = filter_unseen(candidates, seen_ids)
        shortlist = self.build_shortlist(unseen)
        entries = self.rank_entries(shortlist, target_date=target_date)

        subject = build_subject(digest_date, len(entries))
        summary = self.build_summary(entries)
        payload = DigestPayload(
            digest_date=target_date,
            window=window,
            subject=subject,
            entries=entries,
            summary=summary,
        )
        output_dir = self._output_dir_for_date(target_date)
        rendered = self.renderer.render(payload, output_dir=output_dir)
        html_path, pdf_path = self.renderer.write(rendered)
        self._write_manifest(output_dir, payload)

        if send:
            self.settings.require_mail_settings()
            self.rank.auth_check()
            mailer = Mailer(
                host=self.settings.smtp_host or "",
                port=self.settings.smtp_port,
                username=self.settings.smtp_username or "",
                password=self.settings.smtp_password or "",
                sender=self.settings.email_from or "",
            )
            if entries:
                mailer.send_digest(
                    recipients=[self.settings.email_to or ""],
                    subject=subject,
                    html_body=rendered.html,
                    pdf_bytes=rendered.pdf_bytes,
                    pdf_name=f"research-digest-{digest_date}.pdf",
                )
            else:
                mailer.send_text(
                    recipients=[self.settings.email_to or ""],
                    subject=f"Daily Research Digest - {digest_date} (no new papers)",
                    body="No new relevant papers were found in the last 48-hour window.",
                )
            self.state.record_send(
                digest_date=digest_date,
                subject=subject,
                entries=entries,
            )

        return DigestRunResult(
            digest_date=target_date,
            entries=entries,
            output_dir=str(output_dir),
            html_path=html_path,
            pdf_path=pdf_path,
            subject=subject,
            skipped_send=False,
        )

    def preview_digest(self, *, target_date: date) -> DigestRunResult:
        return self.run_digest(target_date=target_date, send=False)

    def backfill(self, *, start_date: date, end_date: date) -> List[DigestRunResult]:
        results: List[DigestRunResult] = []
        current = start_date
        while current <= end_date:
            results.append(self.preview_digest(target_date=current))
            current += timedelta(days=1)
        return results

    def send_failure_email(self, *, target_date: date, error: Exception) -> None:
        if not all([self.settings.smtp_host, self.settings.smtp_username, self.settings.smtp_password, self.settings.email_to, self.settings.email_from]):
            return
        mailer = Mailer(
            host=self.settings.smtp_host or "",
            port=self.settings.smtp_port,
            username=self.settings.smtp_username or "",
            password=self.settings.smtp_password or "",
            sender=self.settings.email_from or "",
        )
        mailer.send_text(
            recipients=[self.settings.email_to or ""],
            subject=f"Daily Research Digest failure - {target_date.isoformat()}",
            body=f"Codex auth or digest execution failed and needs attention.\n\n{error}",
        )

    def collect_candidates(self, window) -> List[PaperRecord]:
        records = self.source_client.fetch_arxiv(window, max_results=self.settings.arxiv_max_results)
        records.extend(
            self.source_client.fetch_openalex(
                window,
                per_page=self.settings.openalex_per_page,
                max_pages=self.settings.openalex_max_pages,
            )
        )
        records = dedupe_records(records)
        records = [record for record in records if record.heuristic_score >= 1.5]
        records.sort(key=lambda paper: (paper.screening_score, paper.published_at), reverse=True)
        enriched: List[PaperRecord] = []
        for record in records[: max(self.settings.codex_shortlist_size, self.settings.top_n)]:
            if not record.abstract or not record.doi:
                try:
                    record = self.source_client.enrich_with_crossref(record)
                except Exception:
                    pass
            enriched.append(record)
        enriched.extend(records[max(self.settings.codex_shortlist_size, self.settings.top_n) :])
        enriched = dedupe_records(enriched)
        enriched.sort(key=lambda paper: (paper.screening_score, paper.published_at), reverse=True)
        return enriched

    def augment_candidates_with_codex_discoveries(self, *, window, target_date: date, candidates: List[PaperRecord]) -> List[PaperRecord]:
        if not self.settings.codex_enable_wildcard_discovery or self.settings.codex_wildcard_candidates <= 0:
            return candidates
        try:
            discovered = self.rank.discover_wildcards(
                target_date=target_date,
                timezone_name=self.settings.timezone_name,
                max_candidates=self.settings.codex_wildcard_candidates,
                existing_candidates=candidates,
            )
        except Exception:
            return candidates

        in_window: List[PaperRecord] = []
        for paper in discovered:
            published_date = paper.published_at.date()
            if window.start_at.date() <= published_date <= window.end_at.date():
                in_window.append(paper)

        merged = dedupe_records(candidates + in_window)
        merged.sort(key=lambda paper: (paper.screening_score, paper.published_at), reverse=True)
        return merged

    def rank_entries(self, candidates: List[PaperRecord], *, target_date: date) -> List[DigestEntry]:
        if not candidates:
            return []
        entries = self.rank.rank(
            candidates=candidates,
            target_date=target_date,
            timezone_name=self.settings.timezone_name,
            top_n=self.settings.top_n,
        )
        entries.sort(key=lambda item: (section_sort_key(item.section), -item.rank_score, item.paper.title))
        return entries

    def build_shortlist(self, candidates: List[PaperRecord]) -> List[PaperRecord]:
        ranked = sorted(candidates, key=lambda paper: (paper.screening_score, paper.published_at), reverse=True)
        shortlist: List[PaperRecord] = []
        selected_ids = set()
        shortlist_target = self.settings.codex_shortlist_size + max(self.settings.robotics_spotlight_count, 0)

        def extend_unique(pool: List[PaperRecord], limit: int) -> None:
            added = 0
            for paper in pool:
                if paper.canonical_id in selected_ids:
                    continue
                shortlist.append(paper)
                selected_ids.add(paper.canonical_id)
                added += 1
                if len(shortlist) >= shortlist_target:
                    return
                if limit and added >= limit:
                    return

        extend_unique(ranked, self.settings.shortlist_core_size)
        if len(shortlist) >= shortlist_target:
            return shortlist[:shortlist_target]

        for section in SECTION_ORDER[:-1]:
            extend_unique(
                [paper for paper in ranked if section in paper.topic_hints],
                self.settings.shortlist_per_section,
            )
            if len(shortlist) >= shortlist_target:
                return shortlist[:shortlist_target]

        for profile in PROFILE_ORDER:
            extend_unique(
                [paper for paper in ranked if profile in paper.profile_hints],
                self.settings.shortlist_per_profile,
            )
            if len(shortlist) >= shortlist_target:
                return shortlist[:shortlist_target]

        if self.settings.robotics_spotlight_count > 0:
            extend_unique(
                [
                    paper
                    for paper in ranked
                    if "Robotics" in paper.topic_hints
                    and paper.heuristic_score >= self.settings.robotics_min_heuristic_score
                ],
                self.settings.robotics_spotlight_count,
            )

        shortlist.sort(key=lambda paper: (paper.screening_score, paper.published_at), reverse=True)
        return shortlist[:shortlist_target]

    def build_summary(self, entries: List[DigestEntry]) -> str:
        if not entries:
            return "No new relevant papers were found in the last 48-hour window."
        section_counts = {}
        for entry in entries:
            section_counts[entry.section] = section_counts.get(entry.section, 0) + 1
        breakdown = ", ".join(
            f"{section}: {count}"
            for section, count in sorted(section_counts.items(), key=lambda item: section_sort_key(item[0]))
        )
        return f"Top {len(entries)} papers selected across {breakdown}."

    def _output_dir_for_date(self, target_date: date) -> Path:
        output_dir = self.settings.output_dir / "digests" / target_date.isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _write_manifest(self, output_dir: Path, payload: DigestPayload) -> None:
        manifest = {
            "digest_date": payload.digest_date.isoformat(),
            "subject": payload.subject,
            "summary": payload.summary,
            "window": {
                "start_at": payload.window.start_at.isoformat(),
                "end_at": payload.window.end_at.isoformat(),
                "timezone": payload.window.timezone_name,
            },
            "entries": [entry.to_dict() for entry in payload.entries],
        }
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
