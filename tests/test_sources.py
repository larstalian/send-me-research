from datetime import date
from pathlib import Path

from send_me_research.config import DEFAULT_ARXIV_CATEGORIES
from send_me_research.normalize import build_window, looks_like_non_abstract_text
from send_me_research.sources import SourceClient, build_arxiv_search_query, format_arxiv_submitted_date


class FakeResponse:
    def __init__(self, *, text="", payload=None, status_code=200):
        self.text = text
        self._payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("bad response")

    def json(self):
        return self._payload


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        if "arxiv.org/api/query" in url:
            return FakeResponse(
                text="""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2503.00001v1</id>
    <updated>2026-03-30T10:00:00Z</updated>
    <title>Agentic Security for LLM Systems</title>
    <summary>We study prompt injection defenses.</summary>
    <author><name>Alice</name></author>
    <link href="https://arxiv.org/abs/2503.00001v1" rel="alternate" type="text/html"/>
    <link href="https://arxiv.org/pdf/2503.00001v1" rel="related" type="application/pdf" title="pdf"/>
    <category term="cs.CL"/>
    <category term="cs.CR"/>
  </entry>
</feed>"""
            )
        return FakeResponse(
            payload={
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": "https://doi.org/10.1000/test",
                        "display_name": "Large Language Models for Defense",
                        "publication_date": "2026-03-30",
                        "authorships": [{"author": {"display_name": "Bob"}}],
                        "primary_location": {
                            "landing_page_url": "https://example.com/openalex",
                            "pdf_url": "https://example.com/openalex.pdf",
                        },
                        "ids": {"openalex": "https://openalex.org/W1", "doi": "https://doi.org/10.1000/test"},
                        "abstract_inverted_index": {"Large": [0], "language": [1], "models": [2]},
                        "concepts": [{"display_name": "Computer security"}],
                    }
                ]
            }
        )

    def close(self):
        return None


def test_fetch_arxiv_normalizes_feed() -> None:
    client = SourceClient()
    client.client = FakeHttpClient()
    window = build_window(date(2026, 3, 30), "America/Los_Angeles")

    papers = client.fetch_arxiv(window, max_results=10)

    assert len(papers) == 1
    assert papers[0].title == "Agentic Security for LLM Systems"
    assert "Cyber" in papers[0].topic_hints


def test_fetch_arxiv_uses_category_filter_and_exact_utc_window_bounds() -> None:
    client = SourceClient()
    client.client = FakeHttpClient()
    window = build_window(date(2026, 4, 20), "America/Los_Angeles")

    client.fetch_arxiv(window, max_results=10, categories=DEFAULT_ARXIV_CATEGORIES)

    url, _ = client.client.calls[0]
    assert "%28cat%3Acs.CL+OR+cat%3Acs.AI" in url
    assert "cat%3Aeess.IV%29" in url
    assert "+AND+" in url
    assert "submittedDate%3A%5B202604190700+TO+202604210659%5D" in url


def test_fetch_arxiv_paginates_to_max_results() -> None:
    client = SourceClient()
    client.client = FakeHttpClient()
    entry = """<entry>
    <id>http://arxiv.org/abs/2503.00001v1</id>
    <updated>2026-03-30T10:00:00Z</updated>
    <title>Agentic Security for LLM Systems</title>
    <summary>We study prompt injection defenses.</summary>
    <author><name>Alice</name></author>
    <link href="https://arxiv.org/abs/2503.00001v1" rel="alternate" type="text/html"/>
  </entry>"""
    client.client.get = lambda url, params=None: (
        client.client.calls.append((url, params))
        or FakeResponse(text=f'<feed xmlns="http://www.w3.org/2005/Atom">{entry * 500}</feed>')
    )
    window = build_window(date(2026, 3, 30), "America/Los_Angeles")

    client.fetch_arxiv(window, max_results=501, categories=DEFAULT_ARXIV_CATEGORIES)

    assert "start=0&max_results=500" in client.client.calls[0][0]
    assert "start=500&max_results=1" in client.client.calls[1][0]


def test_format_arxiv_submitted_date_is_host_timezone_independent() -> None:
    window = build_window(date(2026, 4, 20), "America/Los_Angeles")

    assert format_arxiv_submitted_date(window.start_at) == "202604190700"
    assert format_arxiv_submitted_date(window.end_at) == "202604210659"


def test_build_arxiv_search_query_filters_before_fetching() -> None:
    query = build_arxiv_search_query("202604190700", "202604210659", DEFAULT_ARXIV_CATEGORIES)

    assert query.startswith("%28cat%3Acs.CL")
    assert "cat%3Astat.ML" in query
    assert "cat%3Aeess.SY" in query
    assert "submittedDate%3A%5B202604190700+TO+202604210659%5D" in query


def test_build_arxiv_search_query_allows_empty_category_filter() -> None:
    query = build_arxiv_search_query("202604190700", "202604210659", [])

    assert query == "submittedDate%3A%5B202604190700+TO+202604210659%5D"


def test_fetch_openalex_normalizes_payload() -> None:
    client = SourceClient()
    client.client = FakeHttpClient()
    window = build_window(date(2026, 3, 30), "America/Los_Angeles")

    papers = client.fetch_openalex(window, per_page=1, max_pages=1)

    assert papers
    assert papers[0].title == "Large Language Models for Defense"
    assert papers[0].doi == "https://doi.org/10.1000/test"


def test_fetch_openalex_skips_zenodo_artifact_records() -> None:
    client = SourceClient()
    client.client = FakeHttpClient()
    client.client.get = lambda url, params=None: FakeResponse(
        payload={
            "results": [
                {
                    "id": "https://openalex.org/W7143034417",
                    "doi": "https://doi.org/10.5281/zenodo.19309781",
                    "display_name": "Artifact of AudioHijack (IEEE S&P 2026)",
                    "type": "other",
                    "publication_date": "2026-03-29",
                    "authorships": [{"author": {"display_name": "Meng Chen"}}],
                    "primary_location": {
                        "landing_page_url": "https://doi.org/10.5281/zenodo.19309781",
                        "source": {
                            "display_name": "Zenodo (CERN European Organization for Nuclear Research)",
                        },
                    },
                    "ids": {
                        "openalex": "https://openalex.org/W7143034417",
                        "doi": "https://doi.org/10.5281/zenodo.19309781",
                    },
                    "abstract_inverted_index": {
                        "Hardware": [0],
                        "Requirements": [1],
                        "git": [2],
                        "clone": [3],
                        "uv": [4],
                        "sync": [5],
                    },
                }
            ]
        }
    )
    window = build_window(date(2026, 3, 30), "America/Los_Angeles")

    papers = client.fetch_openalex(window, per_page=1, max_pages=1)

    assert papers == []


def test_non_abstract_heuristic_flags_installation_text() -> None:
    text = """
    Hardware Requirements CPU >= 32GB
    Software Requirements CUDA >= 12.1
    git clone git@github.com:zju-muslab/AudioHijack.git
    pip install uv
    uv sync
    """

    assert looks_like_non_abstract_text(text) is True
