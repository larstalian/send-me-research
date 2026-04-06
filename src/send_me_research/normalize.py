from __future__ import annotations

import hashlib
import html
import re
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

from .models import DateWindow, PaperRecord

ARXIV_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
SECTION_ORDER = ("LLMs", "Agents", "Robotics", "Cyber", "Other relevant")
PROFILE_ORDER = (
    "Post-training",
    "Code Generation",
    "Agentic Fit",
    "Benchmarks & Evals",
    "Inference & Efficiency",
)

NON_ABSTRACT_PATTERNS = (
    r"\bhardware requirements?\b",
    r"\bsoftware requirements?\b",
    r"\benviro?nment setup\b",
    r"\bgit clone\b",
    r"\bpip install\b",
    r"\buv sync\b",
    r"\bsource \.venv/bin/activate\b",
    r"\bdownload (?:the project|the .*?dataset|the .*?data)\b",
    r"\bconfigure api[_ -]?key\b",
    r"\bopenai_api_key\b",
    r"\bgoogle_api_key\b",
    r"\bdashscope_api_key\b",
    r"\broot_dir:\b",
    r"\brun_[a-z0-9_]+\.py\b",
    r"\brun_[a-z0-9_]+\.ipynb\b",
    r"\bnote:\s*it will take\b",
)

NON_PAPER_TITLE_PREFIXES = (
    "artifact of ",
    "artifacts of ",
    "dataset for ",
    "supplementary material for ",
    "code for ",
)

SECTION_KEYWORDS: Dict[str, List[str]] = {
    "LLMs": [
        "large language model",
        "llm",
        "language model",
        "foundation model",
        "transformer",
        "multimodal",
        "rag",
        "reasoning",
        "alignment",
        "inference",
        "synthetic data",
        "retrieval",
    ],
    "Agents": [
        "agent",
        "agentic",
        "tool use",
        "tool-use",
        "multi-agent",
        "planning",
        "orchestration",
        "autonomous",
        "workflow",
    ],
    "Robotics": [
        "robot",
        "robotic",
        "embodied",
        "vision-language-action",
        "vision language action",
        "vla",
        "robot learning",
        "manipulation",
        "navigation",
        "locomotion",
        "grasping",
        "sim2real",
        "policy learning",
    ],
    "Cyber": [
        "cyber",
        "security",
        "malware",
        "phishing",
        "vulnerability",
        "exploit",
        "jailbreak",
        "prompt injection",
        "red team",
        "red-team",
        "adversarial",
        "ctf",
    ],
}

PROFILE_KEYWORDS: Dict[str, List[str]] = {
    "Post-training": [
        "fine-tuning",
        "fine tuning",
        "post-training",
        "post training",
        "instruction tuning",
        "supervised fine-tuning",
        "supervised finetuning",
        "sft",
        "distillation",
        "self-distillation",
        "self distillation",
        "preference optimization",
        "dpo",
        "grpo",
        "reward model",
        "policy optimization",
        "alignment tuning",
    ],
    "Code Generation": [
        "code generation",
        "coding",
        "code model",
        "code synthesis",
        "program synthesis",
        "livecodebench",
        "swe-bench",
        "verifier",
        "execution",
        "unit test",
        "compiler",
    ],
    "Agentic Fit": [
        "agent",
        "agentic",
        "tool use",
        "tool-use",
        "web agent",
        "computer use",
        "planning",
        "multi-step",
        "multi step",
    ],
    "Benchmarks & Evals": [
        "benchmark",
        "evaluation",
        "eval",
        "leaderboard",
        "pass@1",
        "pass@k",
        "harder problems",
        "real-world",
        "real world",
    ],
    "Inference & Efficiency": [
        "inference",
        "test-time",
        "test time",
        "decoding",
        "token distribution",
        "kv-cache",
        "kv cache",
        "compression",
        "efficiency",
    ],
}


def build_window(target_date: date, timezone_name: str) -> DateWindow:
    tz = ZoneInfo(timezone_name)
    start_day = target_date - timedelta(days=1)
    start_at = datetime.combine(start_day, time.min, tzinfo=tz)
    end_at = datetime.combine(target_date, time.max.replace(microsecond=0), tzinfo=tz)
    return DateWindow(target_date=target_date, timezone_name=timezone_name, start_at=start_at, end_at=end_at)


def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return clean_whitespace(html.unescape(text))


def normalize_title(text: str) -> str:
    lowered = clean_whitespace(text).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def title_hash(text: str) -> str:
    digest = hashlib.sha1(normalize_title(text).encode("utf-8")).hexdigest()
    return f"title:{digest}"


def reconstruct_openalex_abstract(index: Optional[Dict[str, List[int]]]) -> str:
    if not index:
        return ""
    items: List[str] = []
    for token, positions in index.items():
        for pos in positions:
            while len(items) <= pos:
                items.append("")
            items[pos] = token
    return clean_whitespace(" ".join(items))


def looks_like_non_abstract_text(text: str) -> bool:
    normalized = clean_whitespace(text).lower()
    if not normalized:
        return False
    pattern_hits = sum(1 for pattern in NON_ABSTRACT_PATTERNS if re.search(pattern, normalized))
    if pattern_hits >= 2:
        return True
    return normalized.startswith(("hardware requirements", "software requirements", "environment setup"))


def looks_like_artifact_title(title: str) -> bool:
    normalized = clean_whitespace(title).lower()
    return any(normalized.startswith(prefix) for prefix in NON_PAPER_TITLE_PREFIXES)


def guess_topic_hints(title: str, abstract: str, extras: Iterable[str] | None = None) -> List[str]:
    haystack = f"{title} {abstract}".lower()
    hints = set()
    for section, keywords in SECTION_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            hints.add(section)
    if extras:
        for item in extras:
            lowered = (item or "").lower()
            if lowered.startswith("cs.cr"):
                hints.add("Cyber")
            if lowered.startswith("cs.ro"):
                hints.add("Robotics")
            if lowered.startswith(("cs.cl", "cs.lg", "cs.ai")):
                hints.add("LLMs")
    if not hints:
        hints.add("Other relevant")
    return [section for section in SECTION_ORDER if section in hints]


def guess_profile_hints(title: str, abstract: str, extras: Iterable[str] | None = None) -> List[str]:
    haystack = f"{title} {abstract}".lower()
    hints = set()
    for profile, keywords in PROFILE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            hints.add(profile)
    if extras:
        for item in extras:
            lowered = (item or "").lower()
            if lowered.startswith(("cs.cl", "cs.ai", "cs.lg")):
                hints.add("Post-training")
    return [profile for profile in PROFILE_ORDER if profile in hints]


def heuristic_relevance_score(record: PaperRecord) -> float:
    text = f"{record.title} {record.abstract}".lower()
    score = 0.0
    for section, keywords in SECTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                score += 2.0 if len(keyword.split()) > 1 else 1.0
    if record.source == "arXiv":
        score += 0.5
    if "LLMs" in record.topic_hints:
        score += 1.5
    if "Agents" in record.topic_hints:
        score += 1.0
    if "Robotics" in record.topic_hints:
        score += 1.0
    if "Cyber" in record.topic_hints:
        score += 1.0
    if record.abstract:
        score += min(len(record.abstract) / 1000.0, 1.0)
    return score


def profile_relevance_score(record: PaperRecord) -> float:
    text = f"{record.title} {record.abstract}".lower()
    score = 0.0
    for profile, keywords in PROFILE_KEYWORDS.items():
        matches = sum(1 for keyword in keywords if keyword in text)
        if not matches:
            continue
        if profile == "Post-training":
            score += min(matches, 4) * 1.6
        elif profile == "Code Generation":
            score += min(matches, 4) * 1.5
        elif profile == "Agentic Fit":
            score += min(matches, 3) * 1.2
        else:
            score += min(matches, 3) * 1.0
    if "Post-training" in record.profile_hints and "Agentic Fit" in record.profile_hints:
        score += 1.5
    if "Code Generation" in record.profile_hints and "Benchmarks & Evals" in record.profile_hints:
        score += 1.0
    if record.source == "arXiv":
        score += 0.5
    return score


def screening_score(record: PaperRecord) -> float:
    return record.heuristic_score + (1.35 * record.profile_score)


def section_from_hints(topic_hints: List[str]) -> str:
    for section in SECTION_ORDER[:-1]:
        if section in topic_hints:
            return section
    return "Other relevant"


def section_sort_key(section: str) -> int:
    try:
        return SECTION_ORDER.index(section)
    except ValueError:
        return len(SECTION_ORDER)


def normalize_arxiv_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_openalex_timestamp(value: str) -> datetime:
    if "T" in value:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.fromisoformat(f"{value}T00:00:00+00:00")


def build_paper_record(
    *,
    title: str,
    abstract: str,
    authors: List[str],
    published_at: datetime,
    source: str,
    landing_url: str,
    pdf_url: Optional[str],
    doi: Optional[str],
    source_ids: List[str],
    extras: Iterable[str] | None = None,
    canonical_id: Optional[str] = None,
) -> PaperRecord:
    sanitized_abstract = clean_whitespace(abstract)
    if looks_like_non_abstract_text(sanitized_abstract):
        sanitized_abstract = ""
    hints = guess_topic_hints(title, sanitized_abstract, extras)
    profile_hints = guess_profile_hints(title, sanitized_abstract, extras)
    record = PaperRecord(
        canonical_id=canonical_id or doi or title_hash(title),
        title=clean_whitespace(title),
        abstract=sanitized_abstract,
        authors=[clean_whitespace(author) for author in authors if clean_whitespace(author)],
        published_at=published_at,
        source=source,
        landing_url=landing_url,
        pdf_url=pdf_url,
        doi=doi,
        source_ids=[item for item in source_ids if item],
        topic_hints=hints,
        profile_hints=profile_hints,
    )
    record.heuristic_score = heuristic_relevance_score(record)
    record.profile_score = profile_relevance_score(record)
    record.screening_score = screening_score(record)
    return record
