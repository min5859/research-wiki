#!/usr/bin/env bash
# Analyze papers using Claude Code CLI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PAPERS_FILE="$ROOT/data/papers.json"
ANALYSIS_DIR="$ROOT/data/analysis"
PROMPT_FILE="$ROOT/prompts/analyze.md"
LOG_FILE="$ROOT/logs/analyze.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*" | tee -a "$LOG_FILE"
}

mkdir -p "$ANALYSIS_DIR"

if [ ! -f "$PAPERS_FILE" ]; then
    error "papers.json not found"
    exit 1
fi

PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")

# Parse papers.json and process each paper
PAPER_COUNT=$(python3 -c "import json; print(len(json.load(open('$PAPERS_FILE'))))")

for i in $(seq 0 $((PAPER_COUNT - 1))); do
    ARXIV_ID=$(python3 -c "import json; print(json.load(open('$PAPERS_FILE'))[$i]['arxiv_id'])")
    TITLE=$(python3 -c "import json; print(json.load(open('$PAPERS_FILE'))[$i]['title'])")
    MD_PATH=$(python3 -c "import json; print(json.load(open('$PAPERS_FILE'))[$i].get('md_path', ''))")
    OUTPUT_FILE="$ANALYSIS_DIR/${ARXIV_ID}_analysis.md"

    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        log "Analysis already exists: $OUTPUT_FILE"
        continue
    fi

    if [ -z "$MD_PATH" ] || [ ! -f "$MD_PATH" ]; then
        error "Markdown not found for $ARXIV_ID, skipping"
        continue
    fi

    log "Analyzing: $TITLE ($ARXIV_ID)"

    PAPER_CONTENT=$(cat "$MD_PATH")

    # Truncate if too long (Claude Code has context limits)
    MAX_CHARS=80000
    if [ ${#PAPER_CONTENT} -gt $MAX_CHARS ]; then
        PAPER_CONTENT="${PAPER_CONTENT:0:$MAX_CHARS}

... (truncated)"
        log "Paper truncated to $MAX_CHARS chars"
    fi

    FULL_PROMPT="$PROMPT_TEMPLATE

---

## 논문 정보
- **제목**: $TITLE
- **arXiv ID**: $ARXIV_ID

## 논문 본문

$PAPER_CONTENT"

    # Run Claude Code CLI (unset CLAUDECODE to allow nested invocation from cron)
    if env -u CLAUDECODE claude -p "$FULL_PROMPT" --output-format text > "$OUTPUT_FILE" 2>>"$LOG_FILE"; then
        # Strip bkit footer if present
        if grep -q "^─.*bkit Feature Usage" "$OUTPUT_FILE" 2>/dev/null; then
            sed -i '/^─.*bkit Feature Usage/,$d' "$OUTPUT_FILE"
            # Remove trailing blank lines
            sed -i -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$OUTPUT_FILE"
        fi
        log "Analysis saved: $OUTPUT_FILE ($(wc -c < "$OUTPUT_FILE") bytes)"
    else
        error "Claude analysis failed for $ARXIV_ID"
        rm -f "$OUTPUT_FILE"
    fi

    # Brief pause between analyses
    sleep 2
done

log "Analysis complete"
