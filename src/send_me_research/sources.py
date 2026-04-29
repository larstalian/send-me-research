from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional
from urllib.parse import quote_plus

import httpx

from .models import DateWindow, PaperRecord
from .normalize import (
    ARXIV_NAMESPACE,
    build_paper_record,
    clean_whitespace,
    looks_like_artifact_title,
    looks_like_non_abstract_text,
    reconstruct_openalex_abstract,
    strip_html,
    normalize_arxiv_timestamp,
    normalize_openalex_timestamp,
)

OPENALEX_QUERIES = [
    "large language model",
    "foundation model",
    "fine-tuning large language model",
    "post-training language model",
    "self-distillation language model",
    "model distillation",
    "code generation language model",
    "coding benchmark llm",
    "tool use benchmark",
    "language agent",
    "agentic systems",
    "multi-agent",
    "embodied ai",
    "robot learning",
    "vision language action",
    "robotics foundation model",
    "cybersecurity ai",
    "prompt injection",
    "red teaming llm",
]
ARXIV_PAGE_SIZE = 500


def format_arxiv_submitted_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def build_arxiv_search_query(start_token: str, end_token: str, categories: Iterable[str]) -> str:
    clean_categories = [category.strip() for category in categories if category.strip()]
    date_query = f"submittedDate:[{start_token} TO {end_token}]"
    if not clean_categories:
        return quote_plus(date_query)
    category_query = " OR ".join(f"cat:{category}" for category in clean_categories)
    return quote_plus(f"({category_query}) AND {date_query}")


@dataclass
class SourceBundle:
    papers: List[PaperRecord]
    diagnostics: Dict[str, int]


class SourceError(RuntimeError):
    pass


class SourceClient:
    def __init__(self, contact_email: Optional[str] = None) -> None:
        headers = {
            "User-Agent": "send-me-research/0.1 (+https://github.com/; contact optional)",
            "Accept": "application/json, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
        self.contact_email = contact_email
        self.client = httpx.Client(timeout=30.0, follow_redirects=True, headers=headers)

    def close(self) -> None:
        self.client.close()

    @staticmethod
    def _should_skip_openalex_work(
        *,
        title: str,
        abstract: str,
        work_type: str,
        source_name: str,
    ) -> bool:
        lowered_source = source_name.lower()
        artifact_title = looks_like_artifact_title(title)
        non_abstract = looks_like_non_abstract_text(abstract)

        if work_type in {"other", "dataset", "reference-entry"} and (artifact_title or non_abstract):
            return True
        if "zenodo" in lowered_source and (artifact_title or non_abstract):
            return True
        return False

    def _get(self, url: str, *, params: Optional[Dict[str, object]] = None, attempts: int = 2) -> httpx.Response:
        last_error: Optional[Exception] = None
        for _ in range(attempts):
            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.HTTPError) as error:
                last_error = error
        raise SourceError(str(last_error) if last_error else f"Failed request for {url}")

    def fetch_arxiv(
        self,
        window: DateWindow,
        max_results: int = 2000,
        categories: Iterable[str] = (),
    ) -> List[PaperRecord]:
        start_token = format_arxiv_submitted_date(window.start_at)
        end_token = format_arxiv_submitted_date(window.end_at)
        query = build_arxiv_search_query(start_token, end_token, categories)

        papers: List[PaperRecord] = []
        for start in range(0, max(max_results, 0), ARXIV_PAGE_SIZE):
            page_size = min(ARXIV_PAGE_SIZE, max_results - start)
            url = (
                "https://export.arxiv.org/api/query"
                f"?search_query={query}&start={start}&max_results={page_size}"
                "&sortBy=submittedDate&sortOrder=descending"
            )
            try:
                response = self._get(url)
            except SourceError:
                return papers
            root = ET.fromstring(response.text)
            entries = root.findall("atom:entry", ARXIV_NAMESPACE)
            if not entries:
                break

            for entry in entries:
                title = entry.findtext("atom:title", default="", namespaces=ARXIV_NAMESPACE)
                summary = entry.findtext("atom:summary", default="", namespaces=ARXIV_NAMESPACE)
                updated = entry.findtext("atom:updated", default="", namespaces=ARXIV_NAMESPACE)
                link = ""
                pdf_url = None
                source_ids: List[str] = []
                categories: List[str] = []

                identifier = entry.findtext("atom:id", default="", namespaces=ARXIV_NAMESPACE)
                if identifier:
                    source_ids.append(identifier.rsplit("/", 1)[-1])

                for link_el in entry.findall("atom:link", ARXIV_NAMESPACE):
                    href = link_el.attrib.get("href", "")
                    if link_el.attrib.get("rel") == "alternate":
                        link = href
                    if link_el.attrib.get("title") == "pdf":
                        pdf_url = href
                for category in entry.findall("atom:category", ARXIV_NAMESPACE):
                    term = category.attrib.get("term")
                    if term:
                        categories.append(term)

                authors = [author.findtext("atom:name", default="", namespaces=ARXIV_NAMESPACE) for author in entry.findall("atom:author", ARXIV_NAMESPACE)]
                if not title or not updated or not link:
                    continue
                published_at = normalize_arxiv_timestamp(updated)
                papers.append(
                    build_paper_record(
                        title=title,
                        abstract=summary,
                        authors=authors,
                        published_at=published_at,
                        source="arXiv",
                        landing_url=link,
                        pdf_url=pdf_url,
                        doi=None,
                        source_ids=source_ids,
                        extras=categories,
                        canonical_id=(source_ids[0] if source_ids else None),
                    )
                )
            if len(entries) < page_size:
                break
        return papers

    def fetch_openalex(self, window: DateWindow, per_page: int = 100, max_pages: int = 2) -> List[PaperRecord]:
        papers: List[PaperRecord] = []
        seen_ids = set()
        filters = (
            f"from_publication_date:{window.start_at.date().isoformat()},"
            f"to_publication_date:{window.end_at.date().isoformat()}"
        )
        mailto_suffix = f"&mailto={self.contact_email}" if self.contact_email else ""

        for query in OPENALEX_QUERIES:
            for page in range(1, max_pages + 1):
                url = (
                    "https://api.openalex.org/works"
                    f"?filter={filters}"
                    f"&search={quote_plus(query)}"
                    f"&per-page={per_page}&page={page}"
                    f"{mailto_suffix}"
                )
                try:
                    response = self._get(url)
                except SourceError:
                    break
                payload = response.json()
                results = payload.get("results", [])
                if not results:
                    break
                for item in results:
                    paper = self._normalize_openalex_work(item)
                    if not paper or paper.canonical_id in seen_ids:
                        continue
                    seen_ids.add(paper.canonical_id)
                    papers.append(paper)
        return papers

    def enrich_with_crossref(self, record: PaperRecord) -> PaperRecord:
        message = None
        if record.doi:
            doi = record.doi.replace("https://doi.org/", "").strip()
            try:
                response = self._get(f"https://api.crossref.org/works/{doi}")
                message = response.json().get("message")
            except SourceError:
                message = None
        if not message:
            try:
                response = self._get(
                    "https://api.crossref.org/works",
                    params={"query.title": record.title, "rows": 1},
                )
                items = response.json().get("message", {}).get("items", [])
                if items:
                    message = items[0]
            except SourceError:
                message = None
        if not message:
            return record

        abstract = record.abstract or strip_html(message.get("abstract") or "")
        doi = record.doi or message.get("DOI")
        landing_url = record.landing_url or message.get("URL") or ""
        pdf_url = record.pdf_url
        for link in message.get("link", []):
            if link.get("content-type") == "application/pdf":
                pdf_url = pdf_url or link.get("URL")
        source_ids = list(dict.fromkeys(record.source_ids + ([message.get("DOI")] if message.get("DOI") else [])))
        updated = record.published_at
        issued = message.get("issued", {}).get("date-parts", [])
        if issued and issued[0]:
            year, month, day = (issued[0] + [1, 1, 1])[:3]
            updated = normalize_openalex_timestamp(f"{year:04d}-{month:02d}-{day:02d}")

        return build_paper_record(
            title=record.title,
            abstract=abstract or record.abstract,
            authors=record.authors,
            published_at=updated,
            source=record.source,
            landing_url=landing_url or record.landing_url,
            pdf_url=pdf_url or record.pdf_url,
            doi=doi,
            source_ids=source_ids,
            extras=record.topic_hints,
            canonical_id=record.canonical_id,
        )

    def _normalize_openalex_work(self, item: Dict[str, object]) -> Optional[PaperRecord]:
        title = clean_whitespace(str(item.get("display_name") or item.get("title") or ""))
        abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))  # type: ignore[arg-type]
        if not title:
            return None
        primary_location = item.get("primary_location") or {}
        primary_source = primary_location.get("source") or {}
        source_name = clean_whitespace(str(primary_source.get("display_name") or ""))
        work_type = clean_whitespace(str(item.get("type") or "")).lower()
        if self._should_skip_openalex_work(
            title=title,
            abstract=abstract,
            work_type=work_type,
            source_name=source_name,
        ):
            return None
        authors = []
        for authorship in item.get("authorships", []):  # type: ignore[union-attr]
            author = authorship.get("author", {})  # type: ignore[union-attr]
            name = author.get("display_name")  # type: ignore[union-attr]
            if name:
                authors.append(str(name))

        open_access = item.get("open_access") or {}
        ids = item.get("ids") or {}
        source_ids = [str(value) for value in ids.values() if value]
        doi = item.get("doi") or ids.get("doi")
        landing_url = (
            primary_location.get("landing_page_url")
            or open_access.get("oa_url")
            or item.get("id")
            or ""
        )
        pdf_url = primary_location.get("pdf_url")
        published_at = normalize_openalex_timestamp(
            str(item.get("publication_date") or item.get("updated_date") or "1970-01-01")
        )
        extras: List[str] = []
        for concept in item.get("concepts", []):  # type: ignore[union-attr]
            display_name = concept.get("display_name")  # type: ignore[union-attr]
            if display_name:
                extras.append(str(display_name))

        canonical_id = str(doi or item.get("id") or source_ids[0] if source_ids else title)
        return build_paper_record(
            title=title,
            abstract=abstract,
            authors=authors,
            published_at=published_at,
            source="OpenAlex",
            landing_url=str(landing_url),
            pdf_url=str(pdf_url) if pdf_url else None,
            doi=str(doi) if doi else None,
            source_ids=source_ids,
            extras=extras,
            canonical_id=canonical_id,
        )
