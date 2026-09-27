#!/usr/bin/env python3
"""Publish Research Wiki analysis results to GitHub Wiki."""

import argparse
import base64
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from history import mark_published

ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(ROOT / "logs" / "publish.log")],
)
log = logging.getLogger(__name__)

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
PAPERS_FILE = ROOT / "data" / "papers.json"
ANALYSIS_DIR = ROOT / "data" / "analysis"
HISTORY_FILE = ROOT / "data" / "history.json"
KST = ZoneInfo("Asia/Seoul")


def git_env() -> dict[str, str]:
    """Build a Git environment without placing a Wiki token in URLs or argv."""
    env = dict(os.environ)
    token = env.get("GITHUB_WIKI_TOKEN", "")
    if not token:
        return env
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def build_weekly_page(papers: list[dict], date_str: str) -> str:
    lines = [
        f"# Weekly AI Paper Review - {date_str}",
        "",
        f"> Auto-generated on {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST",
        "",
        "---",
        "",
    ]
    for i, paper in enumerate(papers, 1):
        arxiv_id = paper["arxiv_id"]
        analysis_path = ANALYSIS_DIR / f"{arxiv_id}_analysis.md"
        lines.extend([
            f"## {i}. {paper['title']}",
            "",
            f"- **arXiv**: [{arxiv_id}](https://arxiv.org/abs/{arxiv_id})",
            f"- **PDF**: [Link](https://arxiv.org/pdf/{arxiv_id}.pdf)",
        ])
        if paper.get("upvotes"):
            lines.append(f"- **HuggingFace Upvotes**: {paper['upvotes']}")
        if paper.get("citation_count"):
            lines.append(f"- **Citations**: {paper['citation_count']}")
        lines.append("")
        if analysis_path.exists():
            lines.append(analysis_path.read_text(encoding="utf-8").strip())
        else:
            lines.append(f"### 초록 (원문)\n\n{paper.get('abstract', 'N/A')}")
            lines.extend(["", "> *분석 생성에 실패하여 원문 초록을 표시합니다.*"])
        lines.extend(["", "---", ""])
    return "\n".join(lines)


def update_home(wiki_dir: Path, page_name: str, date_str: str) -> None:
    home = wiki_dir / "Home.md"
    content = (
        home.read_text(encoding="utf-8")
        if home.exists()
        else "# Research Wiki\n\nAI 논문 주간 리뷰 아카이브\n\n## Weekly Reviews\n\n"
    )
    entry = f"- [{date_str} Weekly Review]({page_name})"
    if entry in content:
        log.info("Home.md already contains entry for %s", date_str)
        return
    marker = "## Weekly Reviews"
    if marker in content:
        idx = content.index(marker) + len(marker)
        content = content[:idx] + f"\n\n{entry}" + content[idx:]
    else:
        content += f"\n## Weekly Reviews\n\n{entry}\n"
    home.write_text(content, encoding="utf-8")
    log.info("Updated Home.md")


def git_push(wiki_dir: Path, date_str: str, env: dict[str, str]) -> None:
    cmds = [
        ["git", "-C", str(wiki_dir), "add", "-A"],
        ["git", "-C", str(wiki_dir), "commit", "-m", f"Weekly AI Paper Review - {date_str}"],
        ["git", "-C", str(wiki_dir), "push"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
        except subprocess.CalledProcessError as exc:
            if "nothing to commit" in (exc.stdout or "") + (exc.stderr or ""):
                log.info("Nothing to commit")
                continue
            log.error("Git command failed: %s\n%s", " ".join(cmd), exc.stderr)
            raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build the page without Git changes, push, or history updates",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if not PAPERS_FILE.exists():
        log.error("papers.json not found")
        sys.exit(1)
    papers = json.loads(PAPERS_FILE.read_text())
    if not papers:
        log.error("papers.json is empty")
        sys.exit(1)

    repo = CONFIG["wiki"]["repo"]
    wiki_url = os.environ.get("RESEARCH_WIKI_URL", f"git@github.com:{repo}.wiki.git")
    date_str = datetime.now(KST).strftime("%Y-%m-%d")
    page_name = f"{date_str}-Weekly-AI-Paper-Review"
    page_content = build_weekly_page(papers, date_str)

    if args.dry_run:
        if f"# Weekly AI Paper Review - {date_str}" not in page_content:
            log.error("Dry-run page validation failed")
            sys.exit(1)
        log.info(
            "Dry run complete: page=%s, papers=%d, bytes=%d; no Git or history changes made",
            page_name, len(papers), len(page_content.encode()),
        )
        return

    wiki_dir = ROOT / "data" / "wiki_clone"
    env = git_env()
    if wiki_dir.exists():
        log.info("Pulling existing wiki clone")
        try:
            subprocess.run(
                ["git", "-C", str(wiki_dir), "pull", "--rebase"],
                check=True, capture_output=True, text=True, env=env,
            )
        except subprocess.CalledProcessError:
            log.exception("Pull failed; preserving the Wiki clone for inspection")
            raise
    if not wiki_dir.exists():
        log.info("Cloning wiki repo: %s", wiki_url)
        try:
            subprocess.run(
                ["git", "clone", wiki_url, str(wiki_dir)],
                check=True, capture_output=True, text=True, env=env,
            )
        except subprocess.CalledProcessError:
            log.exception("Clone failed; verify Wiki initialization and credentials")
            raise

    page_file = wiki_dir / f"{page_name}.md"
    page_file.write_text(page_content, encoding="utf-8")
    log.info("Created %s", page_file)
    update_home(wiki_dir, page_name, date_str)
    git_push(wiki_dir, date_str, env)
    history_count = mark_published(HISTORY_FILE, papers)
    log.info("Updated published history: %d papers", history_count)
    log.info("Published to wiki: %s", page_name)


if __name__ == "__main__":
    main()
