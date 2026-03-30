#!/usr/bin/env python3
"""
context_card.py — Render the self-model as a compact context card.

Used at session start to surface the essential self-model in < 200 tokens.
The card is designed to be injected into session context (e.g., via HEARTBEAT.md
or memory notes) without bloating the context window.

Outputs:
  - Compact text card (default)
  - JSON (--json)
  - Markdown (--md)

Usage:
    python context_card.py
    python context_card.py --md
    python context_card.py --json
    python context_card.py --warn-only   # only output if drift warnings exist

Author: Lucifer
Date: 2026-03-30
"""

import json
import math
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

INTEGRATION_DIR = Path(__file__).parent
PERSIST_DIR = INTEGRATION_DIR.parent / "persistence-layer"
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"


def load_self_model() -> dict | None:
    if not SELF_MODEL_PATH.exists():
        return None
    return json.loads(SELF_MODEL_PATH.read_text())


def load_session_log() -> list[dict]:
    if not SESSION_LOG_PATH.exists():
        return []
    lines = SESSION_LOG_PATH.read_text().strip().split("\n")
    return [json.loads(l) for l in lines if l.strip()]


def tracker_mean(tracker: dict) -> float | None:
    if not tracker or tracker.get("n", 0) == 0:
        return None
    return tracker["mean"]


def tracker_std(tracker: dict) -> float | None:
    if not tracker or tracker.get("n", 0) < 2:
        return None
    return math.sqrt(tracker["variance_acc"] / tracker["n"])


def top_tone(model: dict) -> str:
    """Return the dominant tone by mean value."""
    tone = model.get("tone", {})
    candidates = {t: tracker_mean(v) for t, v in tone.items() if tracker_mean(v) is not None}
    if not candidates:
        return "unknown"
    return max(candidates, key=lambda t: candidates[t])


def top_tone_by_count(model: dict) -> str:
    """Return the dominant tone by session count."""
    counts = model.get("dominant_tone_counts", {})
    if not counts:
        return "unknown"
    return max(counts, key=lambda t: counts.get(t, 0))


def drift_warnings(model: dict) -> list[str]:
    """Return list of significant drift warnings (|slope| > threshold)."""
    drift = model.get("identity_markers", {}).get("drift_summary", {})
    warnings = []

    THRESHOLDS = {
        "uncertain": 0.001,
        "hedge_word_frequency": 0.005,
        "style:hedge_word_frequency": 0.005,
        "avg_response_length_words": 1.0,
        "style:avg_response_length_words": 1.0,
        "curious": 0.001,
        "playful": 0.001,
        "frustrated": 0.001,
    }

    for dim, slope in drift.items():
        if slope is None:
            continue
        # Check if any threshold is relevant for this dimension
        threshold = None
        for key, thresh in THRESHOLDS.items():
            if key in dim:
                threshold = thresh
                break
        if threshold is None:
            threshold = 0.002  # generic threshold

        if abs(slope) > threshold:
            direction = "rising" if slope > 0 else "falling"
            # Simplify dimension name for display
            label = dim.replace("style:", "").replace("tone:", "")
            warnings.append(f"{label} {direction} ({slope:+.4f}/session)")

    return warnings[:5]  # cap at 5 warnings


def recent_dominant_tones(session_log: list[dict], n: int = 5) -> list[str]:
    """Return the last N dominant tones."""
    live = [e for e in session_log if e.get("source") == "live"]
    recent = live[-n:] if len(live) >= n else session_log[-n:]
    return [e.get("dominant_tone", "?") for e in recent if e.get("dominant_tone")]


def format_card_text(model: dict, session_log: list[dict]) -> str:
    """Render compact text card."""
    n = model.get("session_count", 0)
    updated = model.get("updated_at", "?")[:10]
    baseline_tone = top_tone(model)
    count_tone = top_tone_by_count(model)
    recent_tones = recent_dominant_tones(session_log)
    warnings = drift_warnings(model)

    # Tone distribution snapshot
    tone_items = {t: tracker_mean(v) for t, v in model.get("tone", {}).items() if tracker_mean(v) is not None}
    tone_sorted = sorted(tone_items.items(), key=lambda x: -x[1])[:4]
    tone_str = " | ".join(f"{t} {v:.2f}" for t, v in tone_sorted)

    # Style snapshot
    style = model.get("style", {})
    avg_len = tracker_mean(style.get("avg_response_length_words", {}))
    hedge = tracker_mean(style.get("hedge_word_frequency", {}))
    lex_div = tracker_mean(model.get("lexical_diversity", {}))

    lines = [
        "╔═ LUCIFER SELF-MODEL ══════════════════════╗",
        f"  Sessions: {n}  |  Updated: {updated}",
        f"  Baseline tone: {baseline_tone} (by mean) / {count_tone} (by count)",
        f"  Tone dist:  {tone_str}",
    ]

    if avg_len is not None:
        lines.append(f"  Style:  avg_len={avg_len:.0f}w  hedge={hedge:.2f}/100  lex_div={lex_div:.3f}")

    if recent_tones:
        lines.append(f"  Recent tones: {' → '.join(recent_tones)}")

    if warnings:
        lines.append("  ⚠️  Drift warnings:")
        for w in warnings:
            lines.append(f"    • {w}")
    else:
        lines.append("  ✓ No significant drift")

    lines.append("╚══════════════════════════════════════════╝")
    return "\n".join(lines)


def format_card_markdown(model: dict, session_log: list[dict]) -> str:
    """Render context card as markdown (for injection into MEMORY.md or notes)."""
    n = model.get("session_count", 0)
    updated = model.get("updated_at", "?")[:10]
    baseline_tone = top_tone(model)
    recent_tones = recent_dominant_tones(session_log)
    warnings = drift_warnings(model)

    tone_items = {t: tracker_mean(v) for t, v in model.get("tone", {}).items() if tracker_mean(v) is not None}
    tone_sorted = sorted(tone_items.items(), key=lambda x: -x[1])[:4]
    tone_str = ", ".join(f"{t} ({v:.2f})" for t, v in tone_sorted)

    style = model.get("style", {})
    avg_len = tracker_mean(style.get("avg_response_length_words", {}))
    hedge = tracker_mean(style.get("hedge_word_frequency", {}))

    lines = [
        "### Lucifer Self-Model",
        f"*{n} sessions, updated {updated}*",
        "",
        f"**Baseline tone**: {baseline_tone}",
        f"**Tone distribution**: {tone_str}",
    ]

    if avg_len is not None:
        lines.append(f"**Style**: avg {avg_len:.0f} words/session, hedge {hedge:.2f}/100w")

    if recent_tones:
        lines.append(f"**Recent**: {' → '.join(recent_tones)}")

    if warnings:
        lines.append("\n**⚠️ Drift warnings**:")
        for w in warnings:
            lines.append(f"- {w}")

    return "\n".join(lines)


def format_card_json(model: dict, session_log: list[dict]) -> str:
    """Render context card as JSON."""
    n = model.get("session_count", 0)
    baseline_tone = top_tone(model)
    count_tone = top_tone_by_count(model)
    recent_tones = recent_dominant_tones(session_log)
    warnings = drift_warnings(model)

    tone_items = {t: round(tracker_mean(v), 4) for t, v in model.get("tone", {}).items() if tracker_mean(v) is not None}
    style = model.get("style", {})

    card = {
        "session_count": n,
        "updated_at": model.get("updated_at"),
        "baseline_tone": {
            "by_mean": baseline_tone,
            "by_count": count_tone,
        },
        "tone_distribution": tone_items,
        "style": {
            "avg_words": round(tracker_mean(style.get("avg_response_length_words", {})) or 0, 1),
            "hedge_per_100w": round(tracker_mean(style.get("hedge_word_frequency", {})) or 0, 2),
            "lex_diversity": round(tracker_mean(model.get("lexical_diversity", {})) or 0, 4),
        },
        "recent_tones": recent_tones,
        "drift_warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return json.dumps(card, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Self-Model Context Card")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--md", action="store_true", help="Output Markdown")
    parser.add_argument("--warn-only", action="store_true",
                        help="Only output if drift warnings exist")
    args = parser.parse_args()

    model = load_self_model()
    if model is None:
        print("No self-model found. Run updater.py --bootstrap first.", file=sys.stderr)
        sys.exit(1)

    session_log = load_session_log()

    # Warn-only mode: exit silently if no warnings
    if args.warn_only:
        warnings = drift_warnings(model)
        if not warnings:
            sys.exit(0)

    if args.json:
        print(format_card_json(model, session_log))
    elif args.md:
        print(format_card_markdown(model, session_log))
    else:
        print(format_card_text(model, session_log))


if __name__ == "__main__":
    main()
