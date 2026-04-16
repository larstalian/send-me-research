from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
from pypdf import PdfReader

from .config import AudienceProfile
from .models import DigestEntry, PaperRecord
from .normalize import build_paper_record, section_from_hints, title_hash

SchemaRunner = Callable[..., subprocess.CompletedProcess[str]]


class CodexAuthError(RuntimeError):
    pass


AUTH_ERROR_PATTERNS = (
    "failed to refresh token",
    "refresh token was already used",
    "provided authentication token is expired",
    "authentication token is expired",
    "401 unauthorized",
    "please log out and sign in again",
    "please try signing in again",
)


def _auth_recovery_message(details: str) -> str:
    hint = (
        "Codex auth is stale or expired. Run `codex login` locally. "
        "If this is the hosted GitHub workflow, then re-run "
        "`./scripts/sync_github_hosted_secrets.sh` to refresh the uploaded auth snapshot."
    )
    cleaned = details.strip()
    if not cleaned:
        return hint
    return f"{cleaned}\n\n{hint}"


def _maybe_auth_error(details: str) -> CodexAuthError | None:
    normalized = details.lower()
    if any(pattern in normalized for pattern in AUTH_ERROR_PATTERNS):
        return CodexAuthError(_auth_recovery_message(details))
    return None


@dataclass
class CodexRanker:
    codex_bin: str = "codex"
    model: str = "gpt-5.4"
    reasoning_effort: str = "medium"
    enable_search: bool = True
    runner: SchemaRunner = subprocess.run

    def auth_check(self, *, probe_exec: bool = True) -> str:
        result = self.runner(
            [self.codex_bin, "login", "status"],
            check=False,
            capture_output=True,
            text=True,
        )
        output = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0 or "Logged in" not in output:
            auth_error = _maybe_auth_error(output)
            if auth_error:
                raise auth_error
            raise CodexAuthError(output or "Codex login is not active.")
        if not probe_exec:
            return output
        schema = {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        }
        payload = self._run_schema_prompt(
            prompt="Return a JSON object with ok=true.",
            schema=schema,
            temp_prefix="codex-auth-probe-",
            enable_search=False,
        )
        if payload.get("ok") is not True:
            raise RuntimeError("Codex auth probe returned an unexpected payload.")
        return f"{output}\nCodex exec probe succeeded."

    def rank(
        self,
        *,
        candidates: List[PaperRecord],
        target_date: date,
        timezone_name: str,
        top_n: int,
        audience_profile: AudienceProfile,
    ) -> List[DigestEntry]:
        if not candidates:
            return []

        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "canonical_id": {"type": "string"},
                            "section": {"type": "string"},
                            "rank_score": {"type": "number"},
                            "why_it_matters": {"type": "string"},
                            "provenance": {"type": "string"},
                            "signal_score": {"type": "number"},
                            "signal_rationale": {"type": "string"},
                            "keep": {"type": "boolean"},
                        },
                        "required": [
                            "canonical_id",
                            "section",
                            "rank_score",
                            "why_it_matters",
                            "provenance",
                            "signal_score",
                            "signal_rationale",
                            "keep",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "entries"],
            "additionalProperties": False,
        }

        prompt = self._build_prompt(
            candidates,
            target_date=target_date,
            timezone_name=timezone_name,
            top_n=top_n,
            audience_profile=audience_profile,
        )
        by_id = {paper.canonical_id: paper for paper in candidates}
        payload = self._run_schema_prompt(prompt=prompt, schema=schema, temp_prefix="codex-rank-")

        decisions = payload.get("entries", [])
        selected: List[DigestEntry] = []
        for decision in decisions:
            if not decision.get("keep", True):
                continue
            paper = by_id.get(decision["canonical_id"])
            if not paper:
                continue
            selected.append(
                DigestEntry(
                    paper=paper,
                    section=str(decision["section"]),
                    rank_score=float(decision["rank_score"]),
                    why_it_matters=str(decision["why_it_matters"]).strip(),
                    provenance=str(decision.get("provenance") or "").strip(),
                    signal_score=float(decision.get("signal_score") or 0.0),
                    signal_rationale=str(decision.get("signal_rationale") or "").strip(),
                    keep=bool(decision["keep"]),
                )
            )

        selected.sort(key=lambda item: item.rank_score, reverse=True)
        selected = selected[:top_n]
        try:
            return self._enrich_selected_entries(selected)
        except Exception:
            return selected

    def discover_wildcards(
        self,
        *,
        target_date: date,
        timezone_name: str,
        max_candidates: int,
        existing_candidates: List[PaperRecord],
        audience_profile: AudienceProfile,
    ) -> List[PaperRecord]:
        if max_candidates <= 0:
            return []

        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "discoveries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "abstract": {"type": "string"},
                            "authors": {"type": "array", "items": {"type": "string"}},
                            "published_at": {"type": "string"},
                            "source": {"type": "string"},
                            "landing_url": {"type": "string"},
                            "pdf_url": {"type": "string"},
                            "doi": {"type": "string"},
                            "interest_score": {"type": "number"},
                            "why_discovered": {"type": "string"},
                        },
                        "required": [
                            "title",
                            "abstract",
                            "authors",
                            "published_at",
                            "source",
                            "landing_url",
                            "interest_score",
                            "why_discovered",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "discoveries"],
            "additionalProperties": False,
        }
        prompt = self._build_discovery_prompt(
            target_date=target_date,
            timezone_name=timezone_name,
            max_candidates=max_candidates,
            existing_candidates=existing_candidates,
            audience_profile=audience_profile,
        )
        payload = self._run_schema_prompt(prompt=prompt, schema=schema, temp_prefix="codex-discover-")
        discoveries = payload.get("discoveries", [])
        output: List[PaperRecord] = []
        for discovery in discoveries:
            published_at = self._parse_discovery_published_at(str(discovery["published_at"]))
            if not published_at:
                continue
            doi = str(discovery.get("doi") or "").strip() or None
            landing_url = str(discovery.get("landing_url") or "").strip()
            if not landing_url:
                continue
            pdf_url = str(discovery.get("pdf_url") or "").strip() or None
            source = str(discovery.get("source") or "CodexDiscovery").strip() or "CodexDiscovery"
            paper = build_paper_record(
                title=str(discovery["title"]).strip(),
                abstract=str(discovery["abstract"]).strip(),
                authors=[str(author).strip() for author in discovery.get("authors", []) if str(author).strip()],
                published_at=published_at,
                source=source,
                landing_url=landing_url,
                pdf_url=pdf_url,
                doi=doi,
                source_ids=[item for item in [doi, landing_url] if item],
                extras=[source, str(discovery.get("why_discovered") or "")],
                canonical_id=doi or landing_url or title_hash(str(discovery["title"])),
            )
            paper.heuristic_score = max(paper.heuristic_score, float(discovery.get("interest_score") or 0.0))
            output.append(paper)
        return output

    def _build_prompt(
        self,
        candidates: List[PaperRecord],
        *,
        target_date: date,
        timezone_name: str,
        top_n: int,
        audience_profile: AudienceProfile,
    ) -> str:
        priority_line = ", ".join(audience_profile.priority_keywords[:10]) or "general ML relevance"
        lines = [
            "You are curating a daily research digest.",
            f"Digest date: {target_date.isoformat()}",
            f"Timezone: {timezone_name}",
            f"Audience profile: {audience_profile.name}",
            f"Return at most {top_n} kept papers.",
            f"Audience description: {audience_profile.description}",
            f"Priority topics: {priority_line}",
            "Prefer genuinely new, practical, benchmark, systems, attack/defense, and foundational papers over weak keyword matches.",
            "A focused but high-upside post-training or code-generation paper can outrank a noisier paper that merely mentions many trendy keywords.",
            "Use only these sections: LLMs, Agents, Robotics, Cyber, Other relevant.",
            "If there are genuinely strong robotics or embodied-AI papers, include up to 2 of them rather than letting the digest become all generic LLM papers.",
            "If there are clearly more than a handful of solid papers, do not be overly stingy. Fill the digest with up to the requested count.",
            "For each kept paper, write one concise sentence for why_it_matters.",
            "For each kept paper, also provide a concise provenance string naming the most relevant institution, company, lab, venue, or release status you can verify.",
            "Also provide signal_score from 0 to 10 and a short signal_rationale that explains the external signal without over-weighting prestige.",
            "Use signal_score to capture things like strong institutions, serious real-world data, notable venue context, awards, or clear production relevance.",
            "Do not hallucinate awards, affiliations, or venue claims. If uncertain, say the provenance is unclear or that it is an arXiv preprint without evident award signal.",
            "Drop papers that are off-topic, weakly related, or obviously low-signal.",
            "You may use available web search to validate institutions, venue context, awards, or practical significance, but only select from the provided candidates.",
            "",
            "Candidates:",
        ]
        for paper in candidates:
            abstract_excerpt = paper.abstract[:1200]
            lines.extend(
                [
                    json.dumps(
                        {
                            "canonical_id": paper.canonical_id,
                            "title": paper.title,
                            "abstract_excerpt": abstract_excerpt,
                            "authors": paper.authors[:3],
                            "published_at": paper.published_at.isoformat(),
                            "source": paper.source,
                            "landing_url": paper.landing_url,
                            "pdf_url": paper.pdf_url,
                            "doi": paper.doi,
                            "topic_hints": paper.topic_hints,
                            "profile_hints": paper.profile_hints,
                            "heuristic_score": paper.heuristic_score,
                            "profile_score": paper.profile_score,
                            "screening_score": paper.screening_score,
                            "default_section": section_from_hints(paper.topic_hints),
                        },
                        ensure_ascii=True,
                    )
                ]
            )
        return "\n".join(lines)

    def _build_discovery_prompt(
        self,
        *,
        target_date: date,
        timezone_name: str,
        max_candidates: int,
        existing_candidates: List[PaperRecord],
        audience_profile: AudienceProfile,
    ) -> str:
        priority_line = ", ".join(audience_profile.priority_keywords[:10]) or "general ML relevance"
        lines = [
            "You are discovering additional papers for a daily research digest.",
            f"Digest date: {target_date.isoformat()}",
            f"Timezone: {timezone_name}",
            f"Audience profile: {audience_profile.name}",
            f"Find at most {max_candidates} additional papers.",
            "Use web search to discover papers released on the digest date or the day before it.",
            f"Audience description: {audience_profile.description}",
            f"Priority topics: {priority_line}",
            "Only return papers that look genuinely interesting and likely to matter to an ML/LLM/agents/cyber audience.",
            "Do not return anything that appears to already be in the existing candidate list.",
            "Prefer direct paper pages, DOI pages, arXiv pages, conference pages, or publisher pages.",
            "If you are not confident a paper belongs in the time window, do not include it.",
            "Use ISO date format for published_at. Date-only is fine.",
            "Use interest_score on a 0 to 10 scale.",
            "",
            "Existing candidates to avoid duplicating:",
        ]
        for paper in existing_candidates[:20]:
            lines.append(
                json.dumps(
                    {
                        "title": paper.title,
                        "landing_url": paper.landing_url,
                        "doi": paper.doi,
                        "source": paper.source,
                    },
                    ensure_ascii=True,
                )
            )
        return "\n".join(lines)

    def _build_provenance_prompt(self, entries: List[DigestEntry]) -> str:
        lines = [
            "You are enriching selected daily-digest papers with provenance context.",
            "For each paper, provide:",
            "- provenance: one concise sentence naming the most relevant institution, company, lab, venue, or release status you can verify.",
            "- signal_score: 0 to 10 for external validation/provenance signal, not intrinsic paper quality.",
            "- signal_rationale: one concise sentence explaining the score.",
            "Use available web search when helpful, but do not hallucinate affiliations, awards, or acceptance status.",
            "If the paper is only an arXiv preprint, say so plainly.",
            "If affiliation hints are provided, prefer them unless search contradicts them.",
            "",
            "Selected papers:",
        ]
        for entry in entries:
            lines.append(
                json.dumps(
                    {
                        "canonical_id": entry.paper.canonical_id,
                        "title": entry.paper.title,
                        "authors": entry.paper.authors[:6],
                        "source": entry.paper.source,
                        "landing_url": entry.paper.landing_url,
                        "pdf_url": entry.paper.pdf_url,
                        "doi": entry.paper.doi,
                        "why_it_matters": entry.why_it_matters,
                        "affiliation_hint": self._extract_pdf_first_page_hint(entry.paper),
                    },
                    ensure_ascii=True,
                )
            )
        return "\n".join(lines)

    def _run_schema_prompt(
        self,
        *,
        prompt: str,
        schema: Dict[str, object],
        temp_prefix: str,
        enable_search: bool | None = None,
    ) -> Dict[str, object]:
        with tempfile.TemporaryDirectory(prefix=temp_prefix) as temp_dir:
            temp_path = Path(temp_dir)
            schema_path = temp_path / "schema.json"
            output_path = temp_path / "output.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [self.codex_bin]
            use_search = self.enable_search if enable_search is None else enable_search
            if use_search:
                command.append("--search")
            command.extend(
                [
                    "exec",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--color",
                    "never",
                    "--ephemeral",
                    "-c",
                    f'model_reasoning_effort="{self.reasoning_effort}"',
                    "--model",
                    self.model,
                    "--output-schema",
                    str(schema_path),
                    "-o",
                    str(output_path),
                    "-",
                ]
            )
            result = self.runner(
                command,
                input=prompt,
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                details = result.stderr.strip() or result.stdout.strip() or "Codex schema prompt failed."
                auth_error = _maybe_auth_error(details)
                if auth_error:
                    raise auth_error
                raise RuntimeError(details)
            return json.loads(output_path.read_text(encoding="utf-8"))

    def _enrich_selected_entries(self, entries: List[DigestEntry]) -> List[DigestEntry]:
        if not entries:
            return entries

        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "canonical_id": {"type": "string"},
                            "provenance": {"type": "string"},
                            "signal_score": {"type": "number"},
                            "signal_rationale": {"type": "string"},
                        },
                        "required": ["canonical_id", "provenance", "signal_score", "signal_rationale"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["summary", "entries"],
            "additionalProperties": False,
        }
        payload = self._run_schema_prompt(
            prompt=self._build_provenance_prompt(entries),
            schema=schema,
            temp_prefix="codex-provenance-",
        )
        by_id = {entry.paper.canonical_id: entry for entry in entries}
        for item in payload.get("entries", []):
            entry = by_id.get(str(item.get("canonical_id") or ""))
            if not entry:
                continue
            entry.provenance = str(item.get("provenance") or entry.provenance).strip()
            entry.signal_score = float(item.get("signal_score") or entry.signal_score)
            entry.signal_rationale = str(item.get("signal_rationale") or entry.signal_rationale).strip()
        return entries

    def _extract_pdf_first_page_hint(self, paper: PaperRecord) -> str:
        if not paper.pdf_url:
            return ""
        try:
            response = httpx.get(
                paper.pdf_url,
                follow_redirects=True,
                timeout=20.0,
                headers={"User-Agent": "send-me-research/0.1"},
            )
            response.raise_for_status()
            reader = PdfReader(BytesIO(response.content))
            if not reader.pages:
                return ""
            text = reader.pages[0].extract_text() or ""
            return " ".join(text.split())[:1400]
        except Exception:
            return ""

    def _parse_discovery_published_at(self, raw_value: str) -> Optional[datetime]:
        value = raw_value.strip()
        if not value:
            return None
        try:
            if "T" in value:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return datetime.fromisoformat(f"{value}T00:00:00+00:00")
        except ValueError:
            return None
