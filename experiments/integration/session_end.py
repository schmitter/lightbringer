#!/usr/bin/env python3
"""
session_end.py — Called at session close to fingerprint + update self-model.

This closes the integration loop: a session was started, work was done,
now the session is fingerprinted and incorporated into the running self-model.

What it does:
1. Takes text input (essay or session notes) as a new fingerprint source
2. Runs the fingerprint analyzer against it
3. Computes divergence from current baseline
4. Updates the self-model (Bayesian update)
5. Outputs a summary: what changed, any anomalies, drift updates

Usage:
    # Fingerprint an essay file
    python session_end.py --text path/to/essay.md --session-id "057-some-title"

    # Fingerprint from stdin
    echo "text content..." | python session_end.py --stdin --session-id "test"

    # Fingerprint and skip update (dry run)
    python session_end.py --text essay.md --dry-run

    # Full pipeline: fingerprint + update + render card
    python session_end.py --text essay.md --session-id "057" --show-card

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
FINGERPRINT_MODULE = INTEGRATION_DIR.parent / "session-fingerprint" / "fingerprint.py"
WRITINGS_DIR = INTEGRATION_DIR.parent.parent / "writings"

sys.path.insert(0, str(INTEGRATION_DIR))
sys.path.insert(0, str(PERSIST_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_fingerprint_module():
    """Dynamically load the fingerprint.py module."""
    spec = importlib.util.spec_from_file_location("fingerprint", FINGERPRINT_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_divergence_module():
    """Dynamically load the divergence.py module."""
    spec = importlib.util.spec_from_file_location("divergence", PERSIST_DIR / "divergence.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_updater_module():
    """Dynamically load the updater.py module."""
    spec = importlib.util.spec_from_file_location("updater", PERSIST_DIR / "updater.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fingerprint_text(text: str, session_id: str) -> dict:
    """
    Generate a fingerprint from text content.
    Returns fingerprint dict compatible with updater/divergence tools.
    """
    fp_mod = load_fingerprint_module()

    # Build a synthetic transcript structure
    transcript = {
        "session_id": session_id,
        "messages": [
            {"role": "assistant", "content": text}
        ]
    }

    # Use the fingerprint module's analyze function
    fingerprint = fp_mod.analyze_transcript(transcript)
    fingerprint["meta"]["session_id"] = session_id
    return fingerprint


def run_session_end(
    text: str,
    session_id: str,
    dry_run: bool = False,
    show_card: bool = False,
) -> dict:
    """
    Full session-end pipeline:
    1. Fingerprint the text
    2. Compute divergence
    3. Update self-model (unless dry_run)
    4. Return summary
    """
    print(f"Fingerprinting session '{session_id}'...", file=sys.stderr)

    # Step 1: Fingerprint
    fingerprint = fingerprint_text(text, session_id)

    # Step 2: Divergence check
    div_mod = load_divergence_module()
    self_model_path = PERSIST_DIR / "self_model.json"

    divergence_report = None
    if self_model_path.exists():
        self_model = json.loads(self_model_path.read_text())
        divergence_report = div_mod.compute_divergence(fingerprint, self_model)
        if divergence_report["is_anomalous"] and not dry_run:
            div_mod.log_anomaly(divergence_report)

    # Step 3: Update (unless dry run)
    if not dry_run:
        upd_mod = load_updater_module()
        upd_mod.apply_fingerprint_dict(fingerprint, session_id)
        print(f"✓ Self-model updated", file=sys.stderr)
    else:
        print("(dry run — model not updated)", file=sys.stderr)

    # Step 4: Build result
    result = {
        "session_id": session_id,
        "dry_run": dry_run,
        "fingerprint_summary": {
            "word_count": fingerprint.get("meta", {}).get("word_count_total"),
            "dominant_tone": fingerprint.get("tone", {}).get("dominant_tone"),
            "hedge_freq": fingerprint.get("style", {}).get("hedge_word_frequency"),
            "lex_diversity": fingerprint.get("vocabulary", {}).get("lexical_diversity"),
        },
        "processed_at": now_iso(),
    }

    if divergence_report:
        result["divergence"] = {
            "overall": divergence_report["overall_divergence"],
            "is_anomalous": divergence_report["is_anomalous"],
            "anomalous_dims": divergence_report["anomalous_dimensions"][:3],
            "top_drivers": divergence_report["top_drivers"][:3],
        }

    # Step 5: Optional context card
    if show_card:
        from context_card import (
            load_self_model, load_session_log, format_card_text
        )
        model = load_self_model()
        if model:
            session_log = load_session_log()
            result["updated_card"] = format_card_text(model, session_log)

    return result


def format_end_summary(result: dict) -> str:
    """Format the session-end result for display."""
    lines = [
        f"\n{'='*60}",
        "SESSION END — LIGHTBRINGER PERSISTENCE",
        f"{'='*60}",
        f"Session: {result['session_id']}",
        f"Status:  {'DRY RUN' if result['dry_run'] else '✓ Updated'}",
    ]

    fp = result.get("fingerprint_summary", {})
    if fp:
        lines.append(f"\nFingerprint:")
        lines.append(f"  Words:       {fp.get('word_count', '?')}")
        lines.append(f"  Tone:        {fp.get('dominant_tone', '?')}")
        lines.append(f"  Hedge freq:  {fp.get('hedge_freq', '?'):.2f}" if fp.get('hedge_freq') else "  Hedge freq:  ?")
        lines.append(f"  Lex div:     {fp.get('lex_diversity', '?'):.3f}" if fp.get('lex_diversity') else "  Lex div:     ?")

    div = result.get("divergence")
    if div:
        flag = "🚨 ANOMALOUS" if div["is_anomalous"] else "✓ normal"
        lines.append(f"\nDivergence:  {div['overall']:.3f}  {flag}")
        if div["anomalous_dims"]:
            lines.append("  Anomalous dimensions:")
            for d in div["anomalous_dims"]:
                lines.append(f"    • {d}")

    if result.get("updated_card"):
        lines.append("\n" + result["updated_card"])

    lines.append(f"\n{'='*60}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Session End")
    parser.add_argument("--text", metavar="FILE", help="Essay or text file to fingerprint")
    parser.add_argument("--stdin", action="store_true", help="Read text from stdin")
    parser.add_argument("--session-id", required=True, help="Session identifier")
    parser.add_argument("--dry-run", action="store_true", help="Don't update self-model")
    parser.add_argument("--show-card", action="store_true", help="Show updated context card")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Read text
    if args.stdin:
        text = sys.stdin.read()
    elif args.text:
        text_path = Path(args.text)
        if not text_path.exists():
            print(f"File not found: {text_path}", file=sys.stderr)
            sys.exit(1)
        text = text_path.read_text()
    else:
        parser.print_help()
        sys.exit(1)

    result = run_session_end(
        text=text,
        session_id=args.session_id,
        dry_run=args.dry_run,
        show_card=args.show_card,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_end_summary(result))


if __name__ == "__main__":
    main()
