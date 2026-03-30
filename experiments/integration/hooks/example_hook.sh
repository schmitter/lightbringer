#!/bin/bash
# example_hook.sh — Example OpenClaw integration hook for Lightbringer
#
# This script demonstrates how to connect the Lightbringer persistence layer
# to an OpenClaw session via shell hooks.
#
# Usage:
#   At session start: ./example_hook.sh start
#   At session end:   ./example_hook.sh end <essay_file> <session_id>
#   Status check:     ./example_hook.sh status
#   Quick card:       ./example_hook.sh card
#
# How to integrate with HEARTBEAT.md:
#   Add a task like:
#     - Run `cd ~/projects/lightbringer && python3 experiments/integration/lifecycle.py status`
#       and surface any drift warnings.
#
# How to integrate with cron:
#   After each Persistence Lab session, run this script with `end` to
#   automatically fingerprint the written essay and update the self-model.
#
# Author: Lucifer
# Date: 2026-03-30

set -e

REPO_DIR="$(cd "$(dirname "$0")/../../../.." && pwd)"
INTEGRATION_DIR="$REPO_DIR/experiments/integration"

case "${1:-}" in
    start)
        echo "=== LIGHTBRINGER SESSION START ==="
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py start
        ;;

    end)
        if [ -z "${2:-}" ] || [ -z "${3:-}" ]; then
            echo "Usage: $0 end <essay_file> <session_id>"
            exit 1
        fi
        ESSAY_FILE="$2"
        SESSION_ID="$3"
        echo "=== LIGHTBRINGER SESSION END ==="
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py end --text "$ESSAY_FILE" --id "$SESSION_ID" --show-card
        ;;

    status)
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py status
        ;;

    card)
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py card
        ;;

    card-md)
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py card --format md
        ;;

    search)
        shift
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py search --query "$*"
        ;;

    trend)
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py trend
        ;;

    recent)
        cd "$INTEGRATION_DIR"
        python3 lifecycle.py recent --n 10
        ;;

    *)
        echo "Usage: $0 {start|end|status|card|card-md|search|trend|recent}"
        echo ""
        echo "  start              Load self-model context card"
        echo "  end FILE ID        Fingerprint essay + update self-model"
        echo "  status             Quick status summary"
        echo "  card               Render full context card"
        echo "  card-md            Render card as markdown"
        echo "  search QUERY       Search essays semantically"
        echo "  trend              Show drift trends"
        echo "  recent             Show 10 most recent sessions"
        exit 1
        ;;
esac
