#!/bin/bash
# post_session.sh — Run after a Lightbringer writing session.
#
# Called by the writing cron after an essay is committed.
# Handles: companion generation, self-model update, semantic index rebuild.
#
# Usage:
#   ./post_session.sh                    # full pipeline
#   ./post_session.sh --dry-run          # report only
#   ./post_session.sh --with-drift       # also run drift watch
#
# Author: Lucifer
# Date: 2026-04-14

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="${PYTHON:-python3}"

echo "═══════════════════════════════════════"
echo "  Lightbringer Post-Session Pipeline"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "═══════════════════════════════════════"

# Parse args
DRY_RUN=""
WITH_DRIFT=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN="--dry-run" ;;
        --with-drift) WITH_DRIFT="1" ;;
    esac
done

# Step 1: Auto-update pipeline
echo ""
echo "Step 1: Auto-update pipeline"
$PYTHON "$SCRIPT_DIR/auto_update.py" $DRY_RUN

# Step 2: Drift watch (optional)
if [ -n "$WITH_DRIFT" ]; then
    echo ""
    echo "Step 2: Drift watch"
    $PYTHON "$SCRIPT_DIR/drift_watch.py" --force || true
fi

# Step 3: Commit persistence layer changes
if [ -z "$DRY_RUN" ]; then
    echo ""
    echo "Step 3: Commit persistence updates"
    cd "$REPO_ROOT"
    
    # Stage persistence layer files
    git add -A experiments/persistence-layer/ writings/*.fp.json experiments/automation/ 2>/dev/null || true
    
    # Only commit if there are changes
    if git diff --cached --quiet 2>/dev/null; then
        echo "  ✓ No persistence changes to commit"
    else
        ESSAY_COUNT=$(ls writings/*.md 2>/dev/null | wc -l)
        MODEL_SESSIONS=$(python3 -c "import json; m=json.load(open('experiments/persistence-layer/self_model.json')); print(m['session_count'])" 2>/dev/null || echo "?")
        git commit -m "auto: persistence update (${MODEL_SESSIONS} sessions, ${ESSAY_COUNT} essays)" --no-verify 2>/dev/null
        echo "  ✓ Committed persistence updates"
    fi
fi

echo ""
echo "═══════════════════════════════════════"
echo "  Pipeline complete"
echo "═══════════════════════════════════════"
