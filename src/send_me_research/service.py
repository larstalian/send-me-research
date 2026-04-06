from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import List

from .codex_rank import CodexAuthError, CodexRanker
from .config import AppSettings, AudienceProfile
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

    def run_digest(self, *, target_date: date, send: bool, profile_name: str | None = None) -> DigestRunResult:
        profiles = self.settings.resolve_profiles(profile_name)
        if len(profiles) != 1:
            raise ValueError("Multiple digest profiles are configured. Use run_digests() or pass --profile.")
        return self.run_digests(target_date=target_date, send=send, profile_name=profiles[0].name)[0]

    def run_digests(self, *, target_date: date, send: bool, profile_name: str | None = None) -> List[DigestRunResult]:
        window = build_window(target_date, self.settings.timezone_name)
        base_candidates = self.collect_candidates(window)
        results: List[DigestRunResult] = []
        for profile in self.settings.resolve_profiles(profile_name):
            results.append(
                self._run_single_digest(
                    target_date=target_date,
                    send=send,
                    profile=profile,
                    base_candidates=list(base_candidates),
                    window=window,
                )
            )
        return results

    def preview_digest(self, *, target_date: date, profile_name: str | None = None) -> DigestRunResult:
        profiles = self.settings.resolve_profiles(profile_name)
        if len(profiles) != 1:
            raise ValueError("Multiple digest profiles are configured. Use preview_digests() or pass --profile.")
        return self.preview_digests(target_date=target_date, profile_name=profiles[0].name)[0]

    def preview_digests(self, *, target_date: date, profile_name: str | None = None) -> List[DigestRunResult]:
        return self.run_digests(target_date=target_date, send=False, profile_name=profile_name)

    def backfill(self, *, start_date: date, end_date: date, profile_name: str | None = None) -> List[DigestRunResult]:
        results: List[DigestRunResult] = []
        current = start_date
        while current <= end_date:
            results.extend(self.preview_digests(target_date=current, profile_name=profile_name))
            current += timedelta(days=1)
        return results

    def send_failure_email(
        self,
        *,
        target_date: date,
        error: Exception,
        profiles: List[AudienceProfile] | None = None,
    ) -> None:
        if not all([self.settings.smtp_host, self.settings.smtp_username, self.settings.smtp_password, self.settings.email_from]):
            return
        mailer = Mailer(
            host=self.settings.smtp_host or "",
            port=self.settings.smtp_port,
            username=self.settings.smtp_username or "",
            password=self.settings.smtp_password or "",
            sender=self.settings.email_from or "",
        )
        recipients = []
        for profile in profiles or self.settings.load_profiles():
            recipients.extend(profile.recipients)
        recipients = list(dict.fromkeys(recipient for recipient in recipients if recipient))
        if not recipients:
            recipients = self.settings.default_recipients()
        if not recipients:
            return
        mailer.send_text(
            recipients=recipients,
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

    def augment_candidates_with_codex_discoveries(
        self,
        *,
        window,
        target_date: date,
        candidates: List[PaperRecord],
        profile: AudienceProfile,
    ) -> List[PaperRecord]:
        if not self.settings.codex_enable_wildcard_discovery or profile.codex_wildcard_candidates <= 0:
            return candidates
        try:
            discovered = self.rank.discover_wildcards(
                target_date=target_date,
                timezone_name=self.settings.timezone_name,
                max_candidates=profile.codex_wildcard_candidates,
                existing_candidates=candidates,
                audience_profile=profile,
            )
        except Exception:
            return candidates

        in_window: List[PaperRecord] = []
        for paper in discovered:
            published_date = paper.published_at.date()
            if window.start_at.date() <= published_date <= window.end_at.date():
                in_window.append(paper)

        merged = dedupe_records(candidates + in_window)
        merged.sort(key=lambda paper: (self._score_candidate_for_profile(paper, profile), paper.published_at), reverse=True)
        return merged

    def rank_entries(
        self,
        candidates: List[PaperRecord],
        *,
        target_date: date,
        profile: AudienceProfile,
    ) -> List[DigestEntry]:
        if not candidates:
            return []
        entries = self.rank.rank(
            candidates=candidates,
            target_date=target_date,
            timezone_name=self.settings.timezone_name,
            top_n=profile.top_n,
            audience_profile=profile,
        )
        entries.sort(key=lambda item: (section_sort_key(item.section), -item.rank_score, item.paper.title))
        return entries

    def build_shortlist(self, candidates: List[PaperRecord], profile: AudienceProfile) -> List[PaperRecord]:
        ranked = sorted(
            candidates,
            key=lambda paper: (self._score_candidate_for_profile(paper, profile), paper.published_at),
            reverse=True,
        )
        shortlist: List[PaperRecord] = []
        selected_ids = set()
        shortlist_target = profile.codex_shortlist_size + max(profile.robotics_spotlight_count, 0)

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

        extend_unique(ranked, profile.shortlist_core_size)
        if len(shortlist) >= shortlist_target:
            return shortlist[:shortlist_target]

        for section in SECTION_ORDER[:-1]:
            extend_unique([paper for paper in ranked if section in paper.topic_hints], profile.shortlist_per_section)
            if len(shortlist) >= shortlist_target:
                return shortlist[:shortlist_target]

        for profile_hint in PROFILE_ORDER:
            extend_unique(
                [paper for paper in ranked if profile_hint in paper.profile_hints],
                profile.shortlist_per_profile,
            )
            if len(shortlist) >= shortlist_target:
                return shortlist[:shortlist_target]

        if profile.robotics_spotlight_count > 0:
            extend_unique(
                [
                    paper
                    for paper in ranked
                    if "Robotics" in paper.topic_hints
                    and paper.heuristic_score >= self.settings.robotics_min_heuristic_score
                ],
                profile.robotics_spotlight_count,
            )

        shortlist.sort(
            key=lambda paper: (self._score_candidate_for_profile(paper, profile), paper.published_at),
            reverse=True,
        )
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

    def _run_single_digest(
        self,
        *,
        target_date: date,
        send: bool,
        profile: AudienceProfile,
        base_candidates: List[PaperRecord],
        window,
    ) -> DigestRunResult:
        digest_date = target_date.isoformat()
        if send and self.state.digest_already_sent(digest_date, profile.slug):
            output_dir = self._output_dir_for_date(target_date, profile)
            return DigestRunResult(
                profile_name=profile.name,
                digest_date=target_date,
                entries=[],
                output_dir=str(output_dir),
                html_path=str(output_dir / "digest.html"),
                subject=self._subject_for_profile(profile, digest_date, 0),
                skipped_send=True,
            )

        candidates = self.augment_candidates_with_codex_discoveries(
            window=window,
            target_date=target_date,
            candidates=base_candidates,
            profile=profile,
        )
        seen_ids = self.state.load_seen_ids(profile.slug)
        unseen = filter_unseen(candidates, seen_ids)
        shortlist = self.build_shortlist(unseen, profile)
        entries = self.rank_entries(shortlist, target_date=target_date, profile=profile)

        subject = self._subject_for_profile(profile, digest_date, len(entries))
        summary = self.build_summary(entries)
        payload = DigestPayload(
            digest_date=target_date,
            window=window,
            subject=subject,
            entries=entries,
            summary=summary,
        )
        output_dir = self._output_dir_for_date(target_date, profile)
        rendered = self.renderer.render(payload, output_dir=output_dir)
        html_path = self.renderer.write(rendered)
        self._write_manifest(output_dir, payload)

        if send:
            self.settings.require_mail_settings()
            if not profile.recipients:
                raise ValueError(f"Digest profile '{profile.name}' has no recipients configured.")
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
                    recipients=profile.recipients,
                    subject=subject,
                    html_body=rendered.html,
                )
            else:
                mailer.send_text(
                    recipients=profile.recipients,
                    subject=f"{subject} (no new papers)",
                    body="No new relevant papers were found in the last 48-hour window.",
                )
            self.state.record_send(
                digest_date=digest_date,
                subject=subject,
                profile_name=profile.slug,
                output_dir=self._state_output_dir(output_dir),
                entries=entries,
            )

        return DigestRunResult(
            profile_name=profile.name,
            digest_date=target_date,
            entries=entries,
            output_dir=str(output_dir),
            html_path=html_path,
            subject=subject,
            skipped_send=False,
        )

    def _score_candidate_for_profile(self, paper: PaperRecord, profile: AudienceProfile) -> float:
        text = f"{paper.title} {paper.abstract}".lower()
        title = paper.title.lower()
        bonus = 0.0
        for keyword in profile.priority_keywords:
            normalized = keyword.strip().lower()
            if not normalized:
                continue
            if normalized in text:
                bonus += 1.6 if " " in normalized else 0.9
            if normalized in title:
                bonus += 0.6
        return paper.screening_score + min(bonus, 12.0)

    def _subject_for_profile(self, profile: AudienceProfile, digest_date: str, count: int) -> str:
        subject = build_subject(digest_date, count)
        if self._use_profile_subdir():
            return f"{profile.name} - {subject}"
        return subject

    def _output_dir_for_date(self, target_date: date, profile: AudienceProfile) -> Path:
        output_dir = self.settings.output_dir / "digests" / target_date.isoformat()
        if self._use_profile_subdir():
            output_dir = output_dir / profile.slug
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _use_profile_subdir(self) -> bool:
        return self.settings.has_explicit_profiles() or len(self.settings.load_profiles()) > 1

    def _state_output_dir(self, output_dir: Path) -> str:
        try:
            return str(output_dir.relative_to(self.settings.workspace_root))
        except ValueError:
            return output_dir.name

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
