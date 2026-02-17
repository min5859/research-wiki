#!/usr/bin/env python3
"""Discover trending AI papers from HuggingFace Daily Papers and Semantic Scholar."""

import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "discover.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
HISTORY_FILE = ROOT / "data" / "history.json"
OUTPUT_FILE = ROOT / "data" / "papers.json"


def load_history() -> set[str]:
    if HISTORY_FILE.exists():
        return set(json.loads(HISTORY_FILE.read_text()))
    return set()


def save_history(history: set[str]):
    HISTORY_FILE.write_text(json.dumps(sorted(history), indent=2))


def fetch_huggingface(lookback_days: int) -> list[dict]:
    """Fetch papers from HuggingFace Daily Papers API for the past N days."""
    papers = []
    today = datetime.now(UTC).date()

    for i in range(lookback_days):
        date = today - timedelta(days=i)
        url = f"https://huggingface.co/api/daily_papers?date={date}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            for entry in resp.json():
                p = entry.get("paper", {})
                arxiv_id = p.get("id", "")
                if not arxiv_id:
                    continue
                papers.append({
                    "arxiv_id": arxiv_id,
                    "title": p.get("title", ""),
                    "abstract": p.get("summary", ""),
                    "upvotes": entry.get("paper", {}).get("upvotes", 0),
                    "source": "huggingface",
                    "published": p.get("publishedAt", ""),
                })
        except requests.RequestException as e:
            log.warning("HF API failed for %s: %s", date, e)

    # deduplicate by arxiv_id
    seen = set()
    unique = []
    for p in papers:
        if p["arxiv_id"] not in seen:
            seen.add(p["arxiv_id"])
            unique.append(p)
    return unique


def fetch_semantic_scholar(lookback_days: int) -> list[dict]:
    """Fetch recent AI papers from Semantic Scholar sorted by citation count."""
    today = datetime.now(UTC).date()
    start = today - timedelta(days=lookback_days)
    date_range = f"{start}:{today}"

    params = {
        "query": "artificial intelligence",
        "fields": "title,abstract,citationCount,openAccessPdf,publicationDate,externalIds",
        "sort": "citationCount:desc",
        "publicationDateOrYear": date_range,
        "limit": 20,
    }
    headers = {}
    api_key = CONFIG["sources"]["semantic_scholar"].get("api_key", "")
    if api_key:
        headers["x-api-key"] = api_key

    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search/bulk",
            params=params,
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except requests.RequestException as e:
        log.warning("Semantic Scholar API failed: %s", e)
        return []

    papers = []
    for item in data:
        ext = item.get("externalIds", {}) or {}
        arxiv_id = ext.get("ArXiv", "")
        if not arxiv_id:
            continue
        oa_pdf = item.get("openAccessPdf") or {}
        papers.append({
            "arxiv_id": arxiv_id,
            "title": item.get("title", ""),
            "abstract": item.get("abstract", ""),
            "citation_count": item.get("citationCount", 0),
            "open_access_pdf": oa_pdf.get("url", ""),
            "source": "semantic_scholar",
            "published": item.get("publicationDate", ""),
        })
    return papers


def score_and_select(hf_papers: list[dict], s2_papers: list[dict], count: int, history: set[str]) -> list[dict]:
    """Merge and score papers from both sources, return top N."""
    hf_weight = CONFIG["sources"]["huggingface"]["weight"]
    s2_weight = CONFIG["sources"]["semantic_scholar"]["weight"]

    scores: dict[str, dict] = {}

    # Normalize HF upvotes
    max_upvotes = max((p["upvotes"] for p in hf_papers), default=1) or 1
    for p in hf_papers:
        aid = p["arxiv_id"]
        if aid in history:
            continue
        norm_score = (p["upvotes"] / max_upvotes) * hf_weight
        scores[aid] = {
            "arxiv_id": aid,
            "title": p["title"],
            "abstract": p["abstract"],
            "score": norm_score,
            "upvotes": p["upvotes"],
            "citation_count": 0,
            "open_access_pdf": "",
            "published": p["published"],
        }

    # Normalize S2 citations
    max_citations = max((p["citation_count"] for p in s2_papers), default=1) or 1
    for p in s2_papers:
        aid = p["arxiv_id"]
        if aid in history:
            continue
        norm_score = (p["citation_count"] / max_citations) * s2_weight
        if aid in scores:
            scores[aid]["score"] += norm_score
            scores[aid]["citation_count"] = p["citation_count"]
            scores[aid]["open_access_pdf"] = p.get("open_access_pdf", "")
        else:
            scores[aid] = {
                "arxiv_id": aid,
                "title": p["title"],
                "abstract": p["abstract"],
                "score": norm_score,
                "upvotes": 0,
                "citation_count": p["citation_count"],
                "open_access_pdf": p.get("open_access_pdf", ""),
                "published": p["published"],
            }

    ranked = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return ranked[:count]


def main():
    count = CONFIG["papers"]["count"]
    lookback = CONFIG["papers"]["lookback_days"]
    history = load_history()

    log.info("Fetching papers (lookback=%d days, count=%d)", lookback, count)

    hf_papers = []
    if CONFIG["sources"]["huggingface"]["enabled"]:
        hf_papers = fetch_huggingface(lookback)
        log.info("HuggingFace: %d papers found", len(hf_papers))

    s2_papers = []
    if CONFIG["sources"]["semantic_scholar"]["enabled"]:
        s2_papers = fetch_semantic_scholar(lookback)
        log.info("Semantic Scholar: %d papers found", len(s2_papers))

    if not hf_papers and not s2_papers:
        log.error("No papers found from any source")
        sys.exit(1)

    selected = score_and_select(hf_papers, s2_papers, count, history)
    if not selected:
        log.error("No new papers to analyze (all in history)")
        sys.exit(1)

    log.info("Selected %d papers:", len(selected))
    for p in selected:
        log.info("  [%.3f] %s - %s", p["score"], p["arxiv_id"], p["title"])

    OUTPUT_FILE.write_text(json.dumps(selected, indent=2, ensure_ascii=False))
    log.info("Saved to %s", OUTPUT_FILE)

    # Update history
    for p in selected:
        history.add(p["arxiv_id"])
    save_history(history)


if __name__ == "__main__":
    main()
