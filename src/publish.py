#!/usr/bin/env python3
"""Publish analysis results to GitHub Wiki."""

import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "publish.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
PAPERS_FILE = ROOT / "data" / "papers.json"


def build_weekly_page(papers: list[dict], date_str: str) -> str:
    """Build the weekly review markdown page."""
    lines = [
        f"# Weekly AI Paper Review - {date_str}",
        "",
        f"> Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "---",
        "",
    ]

    for i, paper in enumerate(papers, 1):
        arxiv_id = paper["arxiv_id"]
        title = paper["title"]
        analysis_path = ROOT / "data" / "analysis" / f"{arxiv_id}_analysis.md"

        lines.append(f"## {i}. {title}")
        lines.append("")
        lines.append(f"- **arXiv**: [{arxiv_id}](https://arxiv.org/abs/{arxiv_id})")
        lines.append(f"- **PDF**: [Link](https://arxiv.org/pdf/{arxiv_id}.pdf)")

        if paper.get("upvotes"):
            lines.append(f"- **HuggingFace Upvotes**: {paper['upvotes']}")
        if paper.get("citation_count"):
            lines.append(f"- **Citations**: {paper['citation_count']}")

        lines.append("")

        if analysis_path.exists():
            analysis = analysis_path.read_text(encoding="utf-8").strip()
            lines.append(analysis)
        else:
            lines.append(f"### Abstract\n\n{paper.get('abstract', 'N/A')}")

        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def update_home(wiki_dir: Path, page_name: str, date_str: str):
    """Update Home.md with a link to the new weekly page."""
    home = wiki_dir / "Home.md"

    if home.exists():
        content = home.read_text(encoding="utf-8")
    else:
        content = "# Research Wiki\n\nAI 논문 주간 리뷰 아카이브\n\n## Weekly Reviews\n\n"

    entry = f"- [{date_str} Weekly Review]({page_name})"

    if entry in content:
        log.info("Home.md already contains entry for %s", date_str)
        return

    # Insert after "## Weekly Reviews" header
    marker = "## Weekly Reviews"
    if marker in content:
        idx = content.index(marker) + len(marker)
        content = content[:idx] + f"\n\n{entry}" + content[idx:]
    else:
        content += f"\n## Weekly Reviews\n\n{entry}\n"

    home.write_text(content, encoding="utf-8")
    log.info("Updated Home.md")


def git_push(wiki_dir: Path, date_str: str):
    """Commit and push changes to the wiki repo."""
    cmds = [
        ["git", "-C", str(wiki_dir), "add", "-A"],
        ["git", "-C", str(wiki_dir), "commit", "-m", f"Weekly AI Paper Review - {date_str}"],
        ["git", "-C", str(wiki_dir), "push"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in (e.stdout or "") + (e.stderr or ""):
                log.info("Nothing to commit")
                return
            log.error("Git command failed: %s\n%s", " ".join(cmd), e.stderr)
            raise


def main():
    if not PAPERS_FILE.exists():
        log.error("papers.json not found")
        sys.exit(1)

    papers = json.loads(PAPERS_FILE.read_text())
    repo = CONFIG["wiki"]["repo"]
    wiki_url = f"git@github.com:{repo}.wiki.git"
    date_str = datetime.now().strftime("%Y-%m-%d")
    page_name = f"{date_str}-Weekly-AI-Paper-Review"

    # Clone wiki repo to temp dir
    wiki_dir = ROOT / "data" / "wiki_clone"
    if wiki_dir.exists():
        log.info("Pulling existing wiki clone")
        subprocess.run(
            ["git", "-C", str(wiki_dir), "pull", "--rebase"],
            check=True, capture_output=True, text=True,
        )
    else:
        log.info("Cloning wiki repo: %s", wiki_url)
        try:
            subprocess.run(
                ["git", "clone", wiki_url, str(wiki_dir)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError:
            # Wiki might not have any pages yet, init manually
            log.warning("Clone failed (wiki may be empty), initializing")
            wiki_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init"], cwd=str(wiki_dir), check=True, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", wiki_url],
                cwd=str(wiki_dir), check=True, capture_output=True,
            )

    # Build and write weekly page
    page_content = build_weekly_page(papers, date_str)
    page_file = wiki_dir / f"{page_name}.md"
    page_file.write_text(page_content, encoding="utf-8")
    log.info("Created %s", page_file)

    # Update Home.md
    update_home(wiki_dir, page_name, date_str)

    # Push
    git_push(wiki_dir, date_str)
    log.info("Published to wiki: %s", page_name)


if __name__ == "__main__":
    main()
