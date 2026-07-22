#!/usr/bin/env bash
# Research Wiki - Weekly AI Paper Review Pipeline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/cron.log"

# Activate venv if present (for cron environment)
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Ensure Homebrew, nvm, and claude CLI are in PATH (cron doesn't load user profile)
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$HOME/.nvm/versions/node/$(ls "$HOME/.nvm/versions/node/" 2>/dev/null | tail -1)/bin:$PATH"

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/data/pdfs" "$SCRIPT_DIR/data/markdown" "$SCRIPT_DIR/data/analysis"

# Single log sink: route all stdout/stderr to the log file. launchd's StandardOutPath
# also points here, so a tee would write every line twice — echo to the redirected fd instead.
exec >> "$LOG_FILE" 2>&1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [PIPELINE] $*"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*"
}

START_TIME=$(date +%s)
log "========================================="
log "Starting weekly AI paper review pipeline"
log "========================================="

# Step 1: Discover trending papers
log "Step 1/5: Discovering trending papers..."
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/discover.py" 2>>"$LOG_FILE"; then
    log "Step 1 complete"
else
    error "Step 1 failed: discover.py"
    exit 1
fi

# Step 2: Download PDFs
log "Step 2/5: Downloading PDFs..."
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/download.py" 2>>"$LOG_FILE"; then
    log "Step 2 complete"
else
    error "Step 2 failed: download.py"
    exit 1
fi

# Step 3: Convert PDF to Markdown
log "Step 3/5: Converting PDFs to Markdown..."
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/convert.py" 2>>"$LOG_FILE"; then
    log "Step 3 complete"
else
    error "Step 3 failed: convert.py"
    exit 1
fi

# Step 4: Analyze with AI CLI (partial failure allowed — exits 1 only if zero papers succeed)
log "Step 4/5: Analyzing papers with AI CLI..."
STEP4_MARKER="$LOG_DIR/.step4-start"
: > "$STEP4_MARKER"
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/analyze.py" 2>>"$LOG_FILE"; then
    log "Step 4 complete"
else
    # Count only analysis files (re)generated during THIS run, not stale accumulated ones
    ANALYSIS_COUNT=$(find "$SCRIPT_DIR/data/analysis" -name "*_analysis.md" -size +0 -newer "$STEP4_MARKER" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$ANALYSIS_COUNT" -gt 0 ]; then
        log "Step 4 partially failed, but $ANALYSIS_COUNT fresh analysis file(s) from this run — continuing"
    else
        error "Step 4 failed: no fresh analysis files produced this run"
        exit 1
    fi
fi
rm -f "$STEP4_MARKER"

# Step 5: Publish to GitHub Wiki
log "Step 5/5: Publishing to GitHub Wiki..."
if "$SCRIPT_DIR/.venv/bin/python" "$SCRIPT_DIR/src/publish.py" 2>>"$LOG_FILE"; then
    log "Step 5 complete"
else
    error "Step 5 failed: publish.py"
    exit 1
fi

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))
log "========================================="
log "Pipeline complete in ${ELAPSED}s"
log "========================================="
