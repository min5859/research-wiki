#!/usr/bin/env python3
"""Convert downloaded PDFs to Markdown using pymupdf4llm."""

import json
import logging
import sys
from pathlib import Path

import pymupdf4llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "convert.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PAPERS_FILE = ROOT / "data" / "papers.json"
MD_DIR = ROOT / "data" / "markdown"


def convert_pdf(pdf_path: str, arxiv_id: str) -> Path | None:
    """Convert a PDF file to Markdown."""
    dest = MD_DIR / f"{arxiv_id}.md"
    if dest.exists() and dest.stat().st_size > 100:
        log.info("Markdown already exists: %s", dest)
        return dest

    try:
        log.info("Converting %s", pdf_path)
        md_text = pymupdf4llm.to_markdown(pdf_path)
        dest.write_text(md_text, encoding="utf-8")
        log.info("Saved %s (%d chars)", dest, len(md_text))
        return dest
    except Exception as e:
        log.error("Conversion failed for %s: %s", pdf_path, e)
        return None


def main():
    if not PAPERS_FILE.exists():
        log.error("papers.json not found. Run discover.py first.")
        sys.exit(1)

    papers = json.loads(PAPERS_FILE.read_text())
    MD_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    for paper in papers:
        arxiv_id = paper["arxiv_id"]
        pdf_path = paper.get("pdf_path", "")

        if not pdf_path or not Path(pdf_path).exists():
            log.warning("No PDF for %s, using abstract as fallback", arxiv_id)
            # Fallback: save abstract as markdown
            dest = MD_DIR / f"{arxiv_id}.md"
            dest.write_text(
                f"# {paper['title']}\n\n## Abstract\n\n{paper.get('abstract', 'N/A')}\n",
                encoding="utf-8",
            )
            paper["md_path"] = str(dest)
            success += 1
            continue

        result = convert_pdf(pdf_path, arxiv_id)
        if result:
            paper["md_path"] = str(result)
            success += 1
        else:
            # Fallback to abstract
            dest = MD_DIR / f"{arxiv_id}.md"
            dest.write_text(
                f"# {paper['title']}\n\n## Abstract\n\n{paper.get('abstract', 'N/A')}\n",
                encoding="utf-8",
            )
            paper["md_path"] = str(dest)
            success += 1

    PAPERS_FILE.write_text(json.dumps(papers, indent=2, ensure_ascii=False))
    log.info("Converted %d/%d papers", success, len(papers))


if __name__ == "__main__":
    main()
