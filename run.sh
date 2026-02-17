#!/usr/bin/env bash
# Research Wiki - Weekly AI Paper Review Pipeline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/cron.log"

mkdir -p "$LOG_DIR" "$SCRIPT_DIR/data/pdfs" "$SCRIPT_DIR/data/markdown" "$SCRIPT_DIR/data/analysis"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [PIPELINE] $*" | tee -a "$LOG_FILE"
}

error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $*" | tee -a "$LOG_FILE"
}

START_TIME=$(date +%s)
log "========================================="
log "Starting weekly AI paper review pipeline"
log "========================================="

# Step 1: Discover trending papers
log "Step 1/5: Discovering trending papers..."
if python3 "$SCRIPT_DIR/src/discover.py" 2>>"$LOG_FILE"; then
    log "Step 1 complete"
else
    error "Step 1 failed: discover.py"
    exit 1
fi

# Step 2: Download PDFs
log "Step 2/5: Downloading PDFs..."
if python3 "$SCRIPT_DIR/src/download.py" 2>>"$LOG_FILE"; then
    log "Step 2 complete"
else
    error "Step 2 failed: download.py"
    exit 1
fi

# Step 3: Convert PDF to Markdown
log "Step 3/5: Converting PDFs to Markdown..."
if python3 "$SCRIPT_DIR/src/convert.py" 2>>"$LOG_FILE"; then
    log "Step 3 complete"
else
    error "Step 3 failed: convert.py"
    exit 1
fi

# Step 4: Analyze with Claude Code
log "Step 4/5: Analyzing papers with Claude Code..."
if bash "$SCRIPT_DIR/src/analyze.sh" 2>>"$LOG_FILE"; then
    log "Step 4 complete"
else
    error "Step 4 failed: analyze.sh"
    exit 1
fi

# Step 5: Publish to GitHub Wiki
log "Step 5/5: Publishing to GitHub Wiki..."
if python3 "$SCRIPT_DIR/src/publish.py" 2>>"$LOG_FILE"; then
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
