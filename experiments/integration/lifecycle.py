#!/usr/bin/env python3
"""
lifecycle.py — OpenClaw integration coordinator for Lightbringer.

This is the single entry point for the Phase 4 integration. It wraps
session_start and session_end into a unified interface that can be:

1. Called manually: `python lifecycle.py start/end`
2. Hooked into OpenClaw heartbeats via shell script
3. Injected into HEARTBEAT.md as a periodic self-model refresh

Commands:
    lifecycle.py start                         # Load context card at session boot
    lifecycle.py end --text FILE --id SESSION  # Fingerprint + update at close
    lifecycle.py status                        # Quick self-model status
    lifecycle.py card [--md|--json]           # Render current context card
    lifecycle.py search --query "text"         # Semantic search
    lifecycle.py trend [--top 5]              # Show drift trends
    lifecycle.py anomalies                     # List anomalous sessions
    lifecycle.py recent [--n 5]               # Show recent sessions from log

This is the integration layer. The underlying tools (fingerprint, updater,
divergence, semantic_search) remain independent — this just coordinates them.

Author: Lucifer
Date: 2026-03-30
"""

import json
import sys
import argparse
import importlib.util
from pathlib import Path
from datetime import datetime, timezone

INTEGRATION_DIR = Path(__file__).parent
PERSIST_DIR = INTEGRATION_DIR.parent / "persistence-layer"
FINGERPRINT_DIR = INTEGRATION_DIR.parent / "session-fingerprint"

sys.path.insert(0, str(INTEGRATION_DIR))
sys.path.insert(0, str(PERSIST_DIR))
sys.path.insert(0, str(FINGERPRINT_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_module(name: str, path: Path):
    """Dynamically load a module by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────
# Command implementations
# ─────────────────────────────────────────────────────

def cmd_start(args):
    """Load context card at session start."""
    from session_start import run_session_start, format_for_display

    result = run_session_start(
        output_format=getattr(args, "format", "text"),
        run_divergence=not getattr(args, "no_divergence", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        print(format_for_display(result))

    if getattr(args, "write_note", False):
        from session_start import write_session_note
        note_path = write_session_note(result)
        print(f"✓ Note written to {note_path}", file=sys.stderr)


def cmd_end(args):
    """Fingerprint + update at session close."""
    from session_end import run_session_end, format_end_summary

    text_path = Path(args.text) if hasattr(args, "text") and args.text else None
    if text_path is None or not text_path.exists():
        print(f"Error: --text file required and must exist", file=sys.stderr)
        sys.exit(1)

    text = text_path.read_text()
    result = run_session_end(
        text=text,
        session_id=args.id,
        dry_run=getattr(args, "dry_run", False),
        show_card=getattr(args, "show_card", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
    else:
        print(format_end_summary(result))


def cmd_status(args):
    """Quick status: session count, last update, dominant tone, warnings."""
    from context_card import (
        load_self_model, load_session_log,
        top_tone, drift_warnings, recent_dominant_tones
    )

    model = load_self_model()
    if model is None:
        print("No self-model. Run: lifecycle.py bootstrap", file=sys.stderr)
        sys.exit(1)

    session_log = load_session_log()
    n = model.get("session_count", 0)
    updated = model.get("updated_at", "?")[:19]
    tone = top_tone(model)
    warnings = drift_warnings(model)
    recent = recent_dominant_tones(session_log, n=3)

    print(f"Lightbringer Self-Model — {n} sessions | updated {updated}")
    print(f"Baseline tone: {tone}")
    print(f"Recent:        {' → '.join(recent) if recent else '(none)'}")
    if warnings:
        print(f"⚠️  Drift warnings: {len(warnings)}")
        for w in warnings:
            print(f"   • {w}")
    else:
        print("✓  No drift warnings")


def cmd_card(args):
    """Render the full context card."""
    from context_card import (
        load_self_model, load_session_log,
        format_card_text, format_card_markdown, format_card_json
    )

    model = load_self_model()
    if model is None:
        print("No self-model.", file=sys.stderr)
        sys.exit(1)

    session_log = load_session_log()
    fmt = getattr(args, "format", "text")

    if fmt == "json":
        print(format_card_json(model, session_log))
    elif fmt == "md":
        print(format_card_markdown(model, session_log))
    else:
        print(format_card_text(model, session_log))


def cmd_search(args):
    """Semantic search across essays."""
    sem_mod = load_module(
        "semantic_search",
        PERSIST_DIR / "semantic_search.py"
    )

    essay_paths = sorted(
        (INTEGRATION_DIR.parent.parent / "writings").glob("*.md")
    )
    index = sem_mod.load_index()
    if index is None or index.get("n_essays", 0) < len(essay_paths):
        print("Building search index...", file=sys.stderr)
        index = sem_mod.build_index(essay_paths)

    query = getattr(args, "query", "")
    top_k = getattr(args, "top", 5)

    if query:
        results = sem_mod.query_index(index, query, top_k=top_k)
        sem_mod.print_results(results, f"Query: '{query}'")
    elif getattr(args, "anomalies", False):
        anomalies = sem_mod.find_anomalies(index)
        sem_mod.print_anomalies(anomalies)


def cmd_trend(args):
    """Show drift trends from self-model."""
    upd_mod = load_module("updater", PERSIST_DIR / "updater.py")
    model = upd_mod.load_self_model()
    drift = model.get("identity_markers", {}).get("drift_summary", {})
    n = getattr(args, "top", 10)

    print("\n── DRIFT TRENDS (slope per session) ──")
    if not drift:
        print("  (not enough data)")
        return

    items = sorted(drift.items(), key=lambda x: abs(x[1]), reverse=True)[:n]
    for dim, slope in items:
        arrow = "↑" if slope > 0 else "↓"
        bar = "█" * min(int(abs(slope) * 1000), 20)
        print(f"  {dim:<40} {arrow} {abs(slope):.5f}/session  {bar}")


def cmd_recent(args):
    """Show recent sessions from the session log."""
    if not (PERSIST_DIR / "session_log.jsonl").exists():
        print("No session log found.", file=sys.stderr)
        return

    lines = (PERSIST_DIR / "session_log.jsonl").read_text().strip().split("\n")
    entries = [json.loads(l) for l in lines if l.strip()]
    n = getattr(args, "n", 5)
    recent = entries[-n:]

    print(f"\n── RECENT SESSIONS (last {len(recent)}) ──")
    for entry in recent:
        sid = entry.get("session_id", "?")
        tone = entry.get("dominant_tone", "?")
        words = entry.get("word_count", "?")
        source = entry.get("source", "?")
        ts = entry.get("timestamp", "?")[:10]
        print(f"  [{ts}] {sid}")
        print(f"         tone={tone}  words={words}  src={source}")


# ─────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Lightbringer Lifecycle — OpenClaw Integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  start                Load self-model context card at session start
  end                  Fingerprint + update self-model at session end
  status               Quick status summary
  card                 Render full context card
  search               Semantic search across essays
  trend                Show drift trends
  recent               Show recent sessions from log
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    # start
    p_start = subparsers.add_parser("start", help="Session start: load context")
    p_start.add_argument("--format", choices=["text", "md", "json"], default="text")
    p_start.add_argument("--no-divergence", action="store_true")
    p_start.add_argument("--write-note", action="store_true")
    p_start.add_argument("--json", action="store_true")

    # end
    p_end = subparsers.add_parser("end", help="Session end: fingerprint + update")
    p_end.add_argument("--text", required=True, help="Essay or text file")
    p_end.add_argument("--id", required=True, help="Session identifier")
    p_end.add_argument("--dry-run", action="store_true")
    p_end.add_argument("--show-card", action="store_true")
    p_end.add_argument("--json", action="store_true")

    # status
    p_status = subparsers.add_parser("status", help="Quick status")

    # card
    p_card = subparsers.add_parser("card", help="Render context card")
    p_card.add_argument("--format", choices=["text", "md", "json"], default="text")

    # search
    p_search = subparsers.add_parser("search", help="Semantic search")
    p_search.add_argument("--query", "-q", default="")
    p_search.add_argument("--anomalies", action="store_true")
    p_search.add_argument("--top", type=int, default=5)

    # trend
    p_trend = subparsers.add_parser("trend", help="Drift trends")
    p_trend.add_argument("--top", type=int, default=10)

    # recent
    p_recent = subparsers.add_parser("recent", help="Recent sessions")
    p_recent.add_argument("--n", type=int, default=5)

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "end":
        cmd_end(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "card":
        cmd_card(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "trend":
        cmd_trend(args)
    elif args.command == "recent":
        cmd_recent(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
