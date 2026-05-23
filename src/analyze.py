#!/usr/bin/env python3
"""Analyze papers using AI CLI (Claude / Codex / Cursor)."""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROOT / "logs" / "analyze.log"),
    ],
)
log = logging.getLogger(__name__)

CONFIG = yaml.safe_load((ROOT / "config.yaml").read_text())
ANALYSIS_CFG = CONFIG["analysis"]

# Backward compat: old flat config without "provider" key
if "provider" not in ANALYSIS_CFG:
    ANALYSIS_CFG["provider"] = "claude"
    ANALYSIS_CFG.setdefault("claude", {})
    ANALYSIS_CFG["claude"]["model"] = ANALYSIS_CFG.get("model", "sonnet")
    ANALYSIS_CFG["claude"]["api_key"] = ANALYSIS_CFG.get("anthropic_api_key", "")

PAPERS_FILE = ROOT / "data" / "papers.json"
ANALYSIS_DIR = ROOT / "data" / "analysis"
PROMPT_FILE = ROOT / ANALYSIS_CFG.get("prompt_file", "prompts/analyze.md")
MAX_CHARS = 80000


def has_korean(text: str, min_chars: int = 10) -> bool:
    return len(re.findall(r"[가-힣]", text)) >= min_chars


def strip_bkit_footer(text: str) -> str:
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if "bkit Feature Usage" in line and line.startswith("─"):
            return "\n".join(lines[:i]).rstrip()
    return text


# ---------------------------------------------------------------------------
# Provider functions: (prompt, model) -> output text | None
# ---------------------------------------------------------------------------

def run_claude(prompt: str, model: str) -> str | None:
    cfg = ANALYSIS_CFG.get("claude", {})
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    api_key = cfg.get("api_key", "")
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    r = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "text"],
        capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        log.error("claude error: %s", r.stderr.strip()[:200])
        return None
    return strip_bkit_footer(r.stdout)


def run_codex(prompt: str, model: str) -> str | None:
    r = subprocess.run(
        ["codex", "exec", "-", "-m", model, "--full-auto"],
        input=prompt, capture_output=True, text=True,
    )
    if r.returncode != 0:
        log.error("codex error: %s", r.stderr.strip()[:200])
        return None
    return r.stdout


def run_cursor(prompt: str, model: str) -> str | None:
    cfg = ANALYSIS_CFG.get("cursor", {})
    env = dict(os.environ)
    api_key = cfg.get("api_key", "")
    if api_key:
        env["CURSOR_API_KEY"] = api_key
    r = subprocess.run(
        ["cursor", "agent", "-p", prompt, "--model", model, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, env=env,
    )
    if r.returncode != 0:
        log.error("cursor error: %s", r.stderr.strip()[:200])
        return None
    return r.stdout


PROVIDERS = {"claude": run_claude, "codex": run_codex, "cursor": run_cursor}


def check_provider(name: str) -> None:
    cmd = name if name != "cursor" else "cursor"
    if not shutil.which(cmd):
        log.error("%s CLI not found in PATH", cmd)
        sys.exit(1)
    if name == "claude":
        cfg = ANALYSIS_CFG.get("claude", {})
        model = cfg.get("model", "sonnet")
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        api_key = cfg.get("api_key", "")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        log.info("Checking claude CLI authentication (model: %s)...", model)
        r = subprocess.run(
            ["claude", "-p", "Reply with only: OK", "--model", model, "--output-format", "text"],
            capture_output=True, text=True, env=env,
        )
        if r.returncode != 0:
            log.error("claude CLI auth failed. Set api_key in config.yaml or run 'claude login'.")
            sys.exit(1)
        log.info("claude CLI authentication verified")
    else:
        log.info("%s CLI found: %s", name, shutil.which(cmd))


def main() -> None:
    provider_name = ANALYSIS_CFG["provider"]
    if provider_name not in PROVIDERS:
        log.error("Unknown provider: %s (available: %s)", provider_name, ", ".join(PROVIDERS))
        sys.exit(1)

    provider_cfg = ANALYSIS_CFG.get(provider_name, {})
    model = provider_cfg.get("model", "sonnet")
    max_retries = ANALYSIS_CFG.get("max_retries", 2)
    run_fn = PROVIDERS[provider_name]

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    if not PAPERS_FILE.exists():
        log.error("papers.json not found")
        sys.exit(1)

    check_provider(provider_name)
    prompt_template = PROMPT_FILE.read_text()
    papers = json.loads(PAPERS_FILE.read_text())
    success = 0

    for paper in papers:
        arxiv_id = paper["arxiv_id"]
        title = paper["title"]
        output_file = ANALYSIS_DIR / f"{arxiv_id}_analysis.md"

        if output_file.exists() and output_file.stat().st_size > 0:
            log.info("Analysis already exists: %s", output_file)
            success += 1
            continue

        md_path = paper.get("md_path", "")
        if not md_path or not Path(md_path).exists():
            log.error("Markdown not found for %s, skipping", arxiv_id)
            continue

        log.info("Analyzing: %s (%s) [provider=%s, model=%s]", title, arxiv_id, provider_name, model)

        content = Path(md_path).read_text()
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS] + "\n\n... (truncated)"
            log.info("Paper truncated to %d chars", MAX_CHARS)

        prompt = (
            f"{prompt_template}\n\n---\n\n"
            f"## 논문 정보\n- **제목**: {title}\n- **arXiv ID**: {arxiv_id}\n\n"
            f"## 논문 본문\n\n{content}"
        )

        analysis_ok = False
        for attempt in range(1, max_retries + 2):
            if attempt > 1:
                log.info("Retry %d/%d for %s (not in Korean)", attempt - 1, max_retries, arxiv_id)
                time.sleep(3)

            result = run_fn(prompt, model)
            if result and has_korean(result):
                output_file.write_text(result)
                analysis_ok = True
                log.info("Analysis saved: %s (%d bytes)", output_file, len(result.encode()))
                break
            elif result:
                log.error("Attempt %d: output for %s is not in Korean", attempt, arxiv_id)
            else:
                log.error("Attempt %d: CLI error for %s", attempt, arxiv_id)

        if analysis_ok:
            success += 1
        else:
            log.error("All retries exhausted for %s", arxiv_id)

        time.sleep(2)

    if success == 0:
        log.error("No papers were successfully analyzed")
        sys.exit(1)

    log.info("Analysis complete (%d/%d papers)", success, len(papers))


if __name__ == "__main__":
    main()
