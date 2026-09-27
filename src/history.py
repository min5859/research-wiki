"""Helpers for the durable published-paper history."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable


ARXIV_LINK_RE = re.compile(r"^- \*\*arXiv\*\*: \[([^\]]+)\]", re.MULTILINE)


def load_history(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError(f"history must be a JSON string list: {path}")
    return set(data)


def save_history(path: Path, history: Iterable[str]) -> None:
    """Atomically persist paper IDs in deterministic order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(sorted(set(history)), indent=2, ensure_ascii=False) + "\n"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_name = temp_file.name
        os.replace(temp_name, path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def mark_published(path: Path, papers: Iterable[dict]) -> int:
    history = load_history(path)
    history.update(paper["arxiv_id"] for paper in papers)
    save_history(path, history)
    return len(history)


def published_paper_ids(wiki_dir: Path) -> set[str]:
    published: set[str] = set()
    for page in wiki_dir.glob("*-Weekly-AI-Paper-Review.md"):
        published.update(ARXIV_LINK_RE.findall(page.read_text(encoding="utf-8")))
    return published
