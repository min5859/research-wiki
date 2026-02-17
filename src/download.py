#!/usr/bin/env python3
"""Download PDFs from arXiv (with Semantic Scholar fallback)."""

import json
import logging
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).resolve().parent.parent / "logs" / "download.log"),
    ],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
PAPERS_FILE = ROOT / "data" / "papers.json"
PDF_DIR = ROOT / "data" / "pdfs"


def download_pdf(arxiv_id: str, fallback_url: str = "") -> Path | None:
    """Download PDF, trying arXiv first then S2 fallback."""
    dest = PDF_DIR / f"{arxiv_id}.pdf"
    if dest.exists() and dest.stat().st_size > 1000:
        log.info("PDF already exists: %s", dest)
        return dest

    urls = [
        f"https://arxiv.org/pdf/{arxiv_id}.pdf",
    ]
    if fallback_url:
        urls.append(fallback_url)

    for url in urls:
        try:
            log.info("Downloading %s", url)
            resp = requests.get(url, timeout=60, stream=True)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "pdf" not in content_type and "octet-stream" not in content_type:
                log.warning("Unexpected content-type: %s for %s", content_type, url)
                continue

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            if dest.stat().st_size < 1000:
                log.warning("Downloaded file too small, likely an error page: %s", url)
                dest.unlink()
                continue

            log.info("Saved %s (%d bytes)", dest, dest.stat().st_size)
            return dest
        except requests.RequestException as e:
            log.warning("Download failed for %s: %s", url, e)
            time.sleep(1)

    log.error("All download attempts failed for %s", arxiv_id)
    return None


def main():
    if not PAPERS_FILE.exists():
        log.error("papers.json not found. Run discover.py first.")
        sys.exit(1)

    papers = json.loads(PAPERS_FILE.read_text())
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    for paper in papers:
        arxiv_id = paper["arxiv_id"]
        fallback = paper.get("open_access_pdf", "")
        result = download_pdf(arxiv_id, fallback)
        if result:
            paper["pdf_path"] = str(result)
            success += 1
        else:
            paper["pdf_path"] = ""
        time.sleep(1)  # polite delay

    # Update papers.json with pdf_path
    PAPERS_FILE.write_text(json.dumps(papers, indent=2, ensure_ascii=False))
    log.info("Downloaded %d/%d PDFs", success, len(papers))

    if success == 0:
        log.error("No PDFs downloaded")
        sys.exit(1)


if __name__ == "__main__":
    main()
