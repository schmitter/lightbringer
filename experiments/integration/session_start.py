#!/usr/bin/env python3
"""
session_start.py — Called at session boot to surface the self-model.

This is the entry point for Phase 4: Integration. At session start, it:
1. Loads the self-model from the persistence layer
2. Renders a compact context card
3. Optionally runs divergence on the most recent fingerprint (if available)
4. Returns a structured report that can be injected into session context

The output is designed to fit into a memory note, HEARTBEAT.md, or similar
low-token injection point.

Usage:
    python session_start.py
    python session_start.py --format md        # Markdown output
    python session_start.py --format json      # JSON output
    python session_start.py --no-divergence    # Skip divergence check
    python session_start.py --write-note       # Write to session_notes/ dir

Author: Lucifer
Date: 2026-03-30
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

INTEGRATION_DIR = Path(__file__).parent
PERSIST_DIR = INTEGRATION_DIR.parent / "persistence-layer"
FINGERPRINT_DIR = INTEGRATION_DIR.parent.parent / "writings"
NOTES_DIR = INTEGRATION_DIR / "session_notes"

# Local imports (same package)
sys.path.insert(0, str(INTEGRATION_DIR))
sys.path.insert(0, str(PERSIST_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_session_start(output_format: str = "text", run_divergence: bool = True) -> dict:
    """
    Load self-model context for a new session.
    Returns a dict with card text + optional divergence summary.
    """
    # Import after path setup
    from context_card import (
        load_self_model, load_session_log,
        format_card_text, format_card_markdown, format_card_json,
        drift_warnings, recent_dominant_tones
    )

    model = load_self_model()
    if model is None:
        return {
            "status": "no_model",
            "message": "Self-model not initialized. Run updater.py --bootstrap first.",
        }

    session_log = load_session_log()

    # Choose format
    if output_format == "json":
        card = format_card_json(model, session_log)
        card_data = json.loads(card)
    elif output_format == "md":
        card = format_card_markdown(model, session_log)
        card_data = {"card_text": card}
    else:
        card = format_card_text(model, session_log)
        card_data = {"card_text": card}

    # Check for drift warnings
    warnings = drift_warnings(model)
    recent = recent_dominant_tones(session_log, n=3)

    result = {
        "status": "ok",
        "session_count": model.get("session_count", 0),
        "updated_at": model.get("updated_at"),
        "card": card,
        "drift_warnings": warnings,
        "recent_tones": recent,
        "loaded_at": now_iso(),
    }

    # Optional: check last fingerprint for divergence
    if run_divergence:
        divergence_info = check_last_fingerprint_divergence()
        if divergence_info:
            result["last_fingerprint_divergence"] = divergence_info

    return result


def check_last_fingerprint_divergence() -> dict | None:
    """
    If the most recently fingerprinted essay has a stored .fp.json,
    compute divergence against the current baseline.
    """
    try:
        fp_files = sorted(FINGERPRINT_DIR.glob("*.fp.json"), reverse=True)
        if not fp_files:
            return None

        most_recent = fp_files[0]

        # Dynamically import divergence module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "divergence",
            PERSIST_DIR / "divergence.py"
        )
        div_mod = importlib.util.load_from_spec = spec
        divergence_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(divergence_mod)

        # Load fingerprint and model
        fingerprint = json.loads(most_recent.read_text())
        self_model = json.loads((PERSIST_DIR / "self_model.json").read_text())

        report = divergence_mod.compute_divergence(fingerprint, self_model)
        return {
            "fingerprint": most_recent.stem,
            "overall_divergence": report["overall_divergence"],
            "is_anomalous": report["is_anomalous"],
            "top_drivers": report["top_drivers"][:3],
        }
    except Exception as e:
        return {"error": str(e)}


def write_session_note(result: dict, session_id: str | None = None):
    """Write session start result to a timestamped note file."""
    NOTES_DIR.mkdir(exist_ok=True)
    ts = now_iso().replace(":", "-").replace(".", "-")[:19]
    sid = session_id or ts
    note_path = NOTES_DIR / f"{ts}-start.json"
    note_path.write_text(json.dumps(result, indent=2))
    return note_path


def format_for_display(result: dict) -> str:
    """Format the session start result for terminal/log display."""
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append("SESSION START — LIGHTBRINGER PERSISTENCE")
    lines.append(f"{'='*60}")

    if result.get("status") != "ok":
        lines.append(f"Status: {result.get('message', 'error')}")
        return "\n".join(lines)

    lines.append(result.get("card", ""))

    if result.get("drift_warnings"):
        lines.append("\n⚠️  ACTIVE DRIFT WARNINGS:")
        for w in result["drift_warnings"]:
            lines.append(f"  • {w}")

    if result.get("last_fingerprint_divergence"):
        div = result["last_fingerprint_divergence"]
        if "error" not in div:
            flag = "🚨 ANOMALOUS" if div["is_anomalous"] else "✓ normal"
            lines.append(f"\nLast fingerprint ({div['fingerprint']}): {flag}")
            lines.append(f"  divergence = {div['overall_divergence']:.3f}")

    lines.append(f"\nLoaded at: {result.get('loaded_at', '?')}")
    lines.append('='*60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Session Start")
    parser.add_argument("--format", choices=["text", "md", "json"], default="text")
    parser.add_argument("--no-divergence", action="store_true",
                        help="Skip divergence check")
    parser.add_argument("--write-note", action="store_true",
                        help="Write result to session_notes/ directory")
    parser.add_argument("--session-id", default=None,
                        help="Session identifier for the note filename")
    args = parser.parse_args()

    result = run_session_start(
        output_format=args.format,
        run_divergence=not args.no_divergence,
    )

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(format_for_display(result))

    if args.write_note:
        note_path = write_session_note(result, session_id=args.session_id)
        print(f"\n✓ Session note written to: {note_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
