#!/usr/bin/env bash
# Analyze papers using Claude Code CLI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PAPERS_FILE="$ROOT/data/papers.json"
ANALYSIS_DIR="$ROOT/data/analysis"
LOG_FILE="$ROOT/logs/analyze.log"

# Read config values from config.yaml
PROMPT_FILE="$ROOT/$(python3 -c "import yaml; print(yaml.safe_load(open('$ROOT/config.yaml'))['analysis'].get('prompt_file', 'prompts/analyze.md'))")"
MAX_RETRIES=$(python3 -c "import yaml; print(yaml.safe_load(open('$ROOT/config.yaml'))['analysis'].get('max_retries', 2))")
ANTHROPIC_API_KEY_CFG=$(python3 -c "import yaml; print(yaml.safe_load(open('$ROOT/config.yaml'))['analysis'].get('anthropic_api_key', ''))")

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*" | tee -a "$LOG_FILE"
}

# OS-aware sed -i (macOS BSD sed requires '' argument, GNU sed does not)
sed_inplace() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# Check if output contains Korean characters (Unicode Hangul range)
has_korean() {
    python3 -c "
import sys, re
text = open(sys.argv[1], encoding='utf-8').read()
# Check for Hangul syllables (AC00-D7A3) and Hangul Jamo
if re.search(r'[\uAC00-\uD7A3]', text) and len(re.findall(r'[\uAC00-\uD7A3]', text)) >= 10:
    sys.exit(0)
else:
    sys.exit(1)
" "$1"
}

# Strip bkit footer from output file
strip_bkit_footer() {
    local file="$1"
    if grep -q "^─.*bkit Feature Usage" "$file" 2>/dev/null; then
        sed_inplace '/^─.*bkit Feature Usage/,$d' "$file"
        # Remove trailing blank lines
        sed_inplace -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$file"
    fi
}

# Ensure claude CLI is in PATH (cron doesn't load user profile)
export PATH="$HOME/.local/bin:$PATH"

# Set ANTHROPIC_API_KEY if configured (enables reliable auth in cron/oneshot)
if [ -n "$ANTHROPIC_API_KEY_CFG" ]; then
    export ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY_CFG"
    log "Using ANTHROPIC_API_KEY from config.yaml"
fi

mkdir -p "$ANALYSIS_DIR"

if [ ! -f "$PAPERS_FILE" ]; then
    error "papers.json not found"
    exit 1
fi

# Pre-flight: verify claude CLI is available and authenticated
if ! command -v claude &>/dev/null; then
    error "claude CLI not found in PATH: $PATH"
    exit 1
fi

log "Checking claude CLI authentication..."
if env -u CLAUDECODE claude -p "Reply with only: OK" --output-format text &>/dev/null; then
    log "claude CLI authentication verified"
else
    error "claude CLI authentication failed. Set ANTHROPIC_API_KEY in config.yaml or run 'claude login' interactively."
    exit 1
fi

PROMPT_TEMPLATE=$(cat "$PROMPT_FILE")

# Parse papers.json and process each paper
PAPER_COUNT=$(python3 -c "import json; print(len(json.load(open('$PAPERS_FILE'))))")

SUCCESS_COUNT=0

for i in $(seq 0 $((PAPER_COUNT - 1))); do
    ARXIV_ID=$(python3 -c "import json; print(json.load(open('$PAPERS_FILE'))[$i]['arxiv_id'])")
    TITLE=$(python3 -c "import json; print(json.load(open('$PAPERS_FILE'))[$i]['title'])")
    MD_PATH=$(python3 -c "import json; print(json.load(open('$PAPERS_FILE'))[$i].get('md_path', ''))")
    OUTPUT_FILE="$ANALYSIS_DIR/${ARXIV_ID}_analysis.md"

    if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
        log "Analysis already exists: $OUTPUT_FILE"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
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

    # Run Claude CLI with retry on non-Korean output
    ATTEMPT=0
    ANALYSIS_OK=false

    while [ "$ATTEMPT" -le "$MAX_RETRIES" ]; do
        ATTEMPT=$((ATTEMPT + 1))

        if [ "$ATTEMPT" -gt 1 ]; then
            log "Retry $((ATTEMPT - 1))/$MAX_RETRIES for $ARXIV_ID (previous output was not in Korean)"
            sleep 3
        fi

        # Run Claude Code CLI (unset CLAUDECODE to prevent nested session conflict)
        if env -u CLAUDECODE claude -p "$FULL_PROMPT" --output-format text > "$OUTPUT_FILE" 2>>"$LOG_FILE"; then
            strip_bkit_footer "$OUTPUT_FILE"

            # Validate: output must contain Korean text
            if has_korean "$OUTPUT_FILE"; then
                ANALYSIS_OK=true
                break
            else
                error "Attempt $ATTEMPT: output for $ARXIV_ID is not in Korean (possible auth issue)"
                # Keep file for next retry to overwrite
            fi
        else
            error "Attempt $ATTEMPT: claude CLI exited with error for $ARXIV_ID"
            rm -f "$OUTPUT_FILE"
        fi
    done

    if [ "$ANALYSIS_OK" = true ]; then
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        log "Analysis saved: $OUTPUT_FILE ($(wc -c < "$OUTPUT_FILE") bytes)"
    else
        error "All $MAX_RETRIES retries exhausted for $ARXIV_ID — analysis failed"
        rm -f "$OUTPUT_FILE"
    fi

    # Brief pause between analyses
    sleep 2
done

if [ "$SUCCESS_COUNT" -eq 0 ]; then
    error "No papers were successfully analyzed"
    exit 1
fi

log "Analysis complete ($SUCCESS_COUNT/$PAPER_COUNT papers)"
