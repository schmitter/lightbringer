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
# The live corpus the model is *supposed* to describe.
WRITINGS_DIR = INTEGRATION_DIR.parent.parent / "writings"

# Staleness thresholds. The model is a fossil if it is too old in wall-clock
# time OR too far behind the corpus it claims to summarize. Either is enough
# to make the card lie at session-start, so either trips the guard.
STALE_AGE_DAYS = 21          # ~3 weeks without an update
STALE_ESSAY_GAP = 8          # >=8 essays written since the last modeled one
import re as _re


def current_corpus_max() -> int | None:
    """Highest essay number present in writings/ (the live corpus front)."""
    if not WRITINGS_DIR.exists():
        return None
    nums = []
    for p in WRITINGS_DIR.glob("*.md"):
        m = _re.match(r"^(\d{3})-", p.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else None


def last_modeled_essay(model: dict) -> int | None:
    """Highest essay number the model has actually ingested.

    Reads the session_log tail rather than trusting session_count, because
    the bootstrap can inflate the count without advancing the corpus front.
    """
    log = load_session_log()
    best = None
    for e in log:
        sid = str(e.get("session_id", ""))
        m = _re.match(r"^(\d{3})-", sid)
        if m:
            n = int(m.group(1))
            best = n if best is None else max(best, n)
    return best


def staleness_report(model: dict) -> dict:
    """Quantify how far the self-model has drifted from the live corpus.

    The Phase 4 integration would surface this card at session-start as
    "who I am." If the model is frozen, the card silently presents a fossil
    as current. This makes the fossil legible instead.
    """
    reasons = []

    # 1. Wall-clock age of the model.
    age_days = None
    updated = model.get("updated_at")
    if updated:
        try:
            ts = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - ts).days
        except ValueError:
            pass
    if age_days is not None and age_days >= STALE_AGE_DAYS:
        reasons.append(f"model is {age_days}d old (>= {STALE_AGE_DAYS}d)")

    # 2. Corpus gap: essays written since the last one the model saw.
    corpus_max = current_corpus_max()
    modeled_max = last_modeled_essay(model)
    essay_gap = None
    if corpus_max is not None and modeled_max is not None:
        essay_gap = corpus_max - modeled_max
        if essay_gap >= STALE_ESSAY_GAP:
            reasons.append(
                f"{essay_gap} essays unmodeled (corpus at {corpus_max:03d}, "
                f"model stops at {modeled_max:03d})"
            )

    return {
        "is_stale": bool(reasons),
        "age_days": age_days,
        "corpus_max": corpus_max,
        "modeled_max": modeled_max,
        "essay_gap": essay_gap,
        "reasons": reasons,
    }


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

    stale = staleness_report(model)

    lines = [
        "╔═ LUCIFER SELF-MODEL ══════════════════════╗",
    ]
    if stale["is_stale"]:
        lines.append("  ⛔ STALE BASELINE — treat as history, not as now:")
        for r in stale["reasons"]:
            lines.append(f"     • {r}")
    lines += [
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

    stale = staleness_report(model)

    lines = [
        "### Lucifer Self-Model",
        f"*{n} sessions, updated {updated}*",
        "",
    ]
    if stale["is_stale"]:
        lines.append("> ⛔ **STALE BASELINE** — " + "; ".join(stale["reasons"]) +
                     ". Read as history, not as a current portrait.")
        lines.append("")
    lines += [
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
        "staleness": staleness_report(model),
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return json.dumps(card, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Self-Model Context Card")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--md", action="store_true", help="Output Markdown")
    parser.add_argument("--warn-only", action="store_true",
                        help="Only output if drift warnings exist")
    parser.add_argument("--check-stale", action="store_true",
                        help="Exit 2 (and print reasons to stderr) if the "
                             "baseline is stale; for lifecycle gating")
    args = parser.parse_args()

    model = load_self_model()
    if model is None:
        print("No self-model found. Run updater.py --bootstrap first.", file=sys.stderr)
        sys.exit(1)

    session_log = load_session_log()

    # Check-stale mode: a gate the lifecycle can call before trusting the card.
    if args.check_stale:
        stale = staleness_report(model)
        if stale["is_stale"]:
            print("STALE: " + "; ".join(stale["reasons"]), file=sys.stderr)
            sys.exit(2)
        print("fresh", file=sys.stderr)
        sys.exit(0)

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
