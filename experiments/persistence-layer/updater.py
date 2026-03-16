#!/usr/bin/env python3
"""
updater.py — Session fingerprint updater for the Lightbringer persistence layer.

Takes a new session fingerprint and updates the running self_model.json using
Bayesian incremental averaging. Appends to session_log.jsonl. Tracks drift history.

Usage:
    python updater.py --fingerprint path/to/fp.json      # update from file
    python updater.py --bootstrap path/to/corpus.json    # bootstrap from corpus
    python updater.py --show                             # print current self model

Author: Lucifer
Date: 2026-03-16
"""

import json
import math
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

PERSIST_DIR = Path(__file__).parent
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"


# ---------------------------------------------------------------------------
# Self-model schema + initialization
# ---------------------------------------------------------------------------

STYLE_FIELDS = [
    "avg_response_length_words",
    "question_to_statement_ratio",
    "sentence_avg_length_words",
    "paragraph_avg_length_sentences",
    "hedge_word_frequency",
    "exclamation_frequency",
    "emoji_frequency",
]

TONE_FIELDS = [
    "curious", "playful", "focused", "frustrated",
    "reflective", "confident", "uncertain",
]

DOMAIN_FIELDS = ["technical", "philosophical", "casual", "emotional"]


def empty_tracked() -> dict:
    """Return an empty running-stats tracker for a numeric dimension."""
    return {"mean": 0.0, "variance_acc": 0.0, "n": 0}


def welford_update(tracker: dict, value: float) -> dict:
    """
    Welford's online algorithm for mean + variance.
    Returns updated tracker.
    """
    if value is None:
        return tracker
    t = dict(tracker)
    t["n"] += 1
    n = t["n"]
    old_mean = t["mean"]
    t["mean"] = old_mean + (value - old_mean) / n
    t["variance_acc"] = t["variance_acc"] + (value - old_mean) * (value - t["mean"])
    return t


def tracker_stats(tracker: dict) -> dict:
    """Return mean and std from a Welford tracker."""
    n = tracker["n"]
    if n == 0:
        return {"mean": None, "std": None, "n": 0}
    std = math.sqrt(tracker["variance_acc"] / n) if n > 1 else 0.0
    return {"mean": round(tracker["mean"], 4), "std": round(std, 4), "n": n}


def init_self_model() -> dict:
    """Return a fresh, empty self-model."""
    style = {f: empty_tracked() for f in STYLE_FIELDS}
    tone = {t: empty_tracked() for t in TONE_FIELDS}
    domain = {d: empty_tracked() for d in DOMAIN_FIELDS}
    lex_div = empty_tracked()

    return {
        "version": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "session_count": 0,
        "style": style,
        "tone": tone,
        "domain": domain,
        "lexical_diversity": lex_div,
        "dominant_tone_counts": {t: 0 for t in TONE_FIELDS},
        "identity_markers": {
            "core_topics": [],
            "signature_phrases": [],
            "drift_summary": {},
        },
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------

def load_self_model() -> dict:
    if SELF_MODEL_PATH.exists():
        return json.loads(SELF_MODEL_PATH.read_text())
    return init_self_model()


def save_self_model(model: dict):
    model["updated_at"] = now_iso()
    SELF_MODEL_PATH.write_text(json.dumps(model, indent=2))


def load_drift_history() -> dict:
    if DRIFT_HISTORY_PATH.exists():
        return json.loads(DRIFT_HISTORY_PATH.read_text())
    return {f: [] for f in STYLE_FIELDS + TONE_FIELDS + DOMAIN_FIELDS + ["lexical_diversity"]}


def save_drift_history(history: dict):
    DRIFT_HISTORY_PATH.write_text(json.dumps(history, indent=2))


def append_session_log(entry: dict):
    with open(SESSION_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Core update logic
# ---------------------------------------------------------------------------

def extract_values(fingerprint: dict) -> dict:
    """Pull all tracked numeric values from a fingerprint dict."""
    style = fingerprint.get("style", {})
    tone_dist = fingerprint.get("tone", {}).get("distribution", {})
    domain_dist = fingerprint.get("vocabulary", {}).get("domain_distribution", {})
    vocab = fingerprint.get("vocabulary", {})

    values = {}
    for f in STYLE_FIELDS:
        values[f"style:{f}"] = style.get(f)
    for t in TONE_FIELDS:
        values[f"tone:{t}"] = tone_dist.get(t)
    for d in DOMAIN_FIELDS:
        values[f"domain:{d}"] = domain_dist.get(d)
    values["lexical_diversity"] = vocab.get("lexical_diversity")

    return values


def update_self_model(model: dict, fingerprint: dict, history: dict) -> tuple[dict, dict]:
    """
    Apply one fingerprint to the running self-model.
    Returns (updated_model, updated_history).
    """
    values = extract_values(fingerprint)
    model = dict(model)

    # Update style trackers
    for f in STYLE_FIELDS:
        key = f"style:{f}"
        if values.get(key) is not None:
            model["style"][f] = welford_update(model["style"][f], values[key])
        history.setdefault(f, []).append(values.get(key))

    # Update tone trackers
    for t in TONE_FIELDS:
        key = f"tone:{t}"
        if values.get(key) is not None:
            model["tone"][t] = welford_update(model["tone"][t], values[key])
        history.setdefault(t, []).append(values.get(key))

    # Update domain trackers
    for d in DOMAIN_FIELDS:
        key = f"domain:{d}"
        if values.get(key) is not None:
            model["domain"][d] = welford_update(model["domain"][d], values[key])
        history.setdefault(d, []).append(values.get(key))

    # Lexical diversity
    if values.get("lexical_diversity") is not None:
        model["lexical_diversity"] = welford_update(
            model["lexical_diversity"], values["lexical_diversity"]
        )
    history.setdefault("lexical_diversity", []).append(values.get("lexical_diversity"))

    # Dominant tone counts
    dominant = fingerprint.get("tone", {}).get("dominant_tone")
    if dominant:
        counts = model.setdefault("dominant_tone_counts", {t: 0 for t in TONE_FIELDS})
        counts[dominant] = counts.get(dominant, 0) + 1

    # Session count
    model["session_count"] = model.get("session_count", 0) + 1

    # Update signature phrases (aggregate top N unique)
    sig = fingerprint.get("vocabulary", {}).get("signature_phrases", [])
    existing = set(model.get("identity_markers", {}).get("signature_phrases", []))
    existing.update(sig)
    # Keep most-seen (we can track counts in a future version)
    model.setdefault("identity_markers", {})["signature_phrases"] = sorted(existing)[:50]

    return model, history


def compute_trend_slopes(history: dict) -> dict:
    """
    Fit a linear slope to each tracked dimension's history.
    Returns {dimension: slope_per_session}.
    """
    slopes = {}
    for dim, vals in history.items():
        clean = [v for v in vals if v is not None]
        n = len(clean)
        if n < 3:
            slopes[dim] = None
            continue
        xs = list(range(n))
        x_mean = sum(xs) / n
        y_mean = sum(clean) / n
        numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, clean))
        denom = sum((x - x_mean) ** 2 for x in xs)
        slopes[dim] = round(numer / denom, 6) if denom != 0 else 0.0
    return slopes


# ---------------------------------------------------------------------------
# Bootstrap from corpus
# ---------------------------------------------------------------------------

def bootstrap_from_corpus(corpus_path: Path):
    """
    Initialize the persistence layer from an existing corpus_summary.json.
    """
    corpus = json.loads(corpus_path.read_text())
    fingerprints = corpus.get("fingerprints", [])

    if not fingerprints:
        print("No fingerprints found in corpus.", file=sys.stderr)
        return

    print(f"Bootstrapping from {len(fingerprints)} corpus fingerprints...", file=sys.stderr)

    model = init_self_model()
    history = load_drift_history()

    for fp in fingerprints:
        session_id = fp.get("meta", {}).get("session_id", "unknown")
        model, history = update_self_model(model, fp, history)
        entry = {
            "session_id": session_id,
            "timestamp": fp.get("meta", {}).get("date", now_iso()),
            "fingerprint_hash": fp.get("fingerprint_hash", ""),
            "dominant_tone": fp.get("tone", {}).get("dominant_tone"),
            "word_count": fp.get("meta", {}).get("word_count_total"),
            "hedge_freq": fp.get("style", {}).get("hedge_word_frequency"),
            "source": "bootstrap",
        }
        append_session_log(entry)
        print(f"  ✓ {session_id}", file=sys.stderr)

    # Compute and embed trend slopes
    slopes = compute_trend_slopes(history)
    model.setdefault("identity_markers", {})["drift_summary"] = {
        k: v for k, v in slopes.items() if v is not None and abs(v) > 0.0001
    }

    save_self_model(model)
    save_drift_history(history)

    print(f"\n✓ Self-model bootstrapped from {model['session_count']} sessions", file=sys.stderr)
    print(f"  Saved to {SELF_MODEL_PATH}", file=sys.stderr)
    return model


# ---------------------------------------------------------------------------
# Apply a single fingerprint
# ---------------------------------------------------------------------------

def apply_fingerprint(fp_path: Path):
    """Load a fingerprint JSON and apply it to the self-model."""
    fingerprint = json.loads(fp_path.read_text())
    model = load_self_model()
    history = load_drift_history()

    model, history = update_self_model(model, fingerprint, history)

    session_id = fingerprint.get("meta", {}).get("session_id", fp_path.stem)
    entry = {
        "session_id": session_id,
        "timestamp": now_iso(),
        "fingerprint_hash": fingerprint.get("fingerprint_hash", ""),
        "dominant_tone": fingerprint.get("tone", {}).get("dominant_tone"),
        "word_count": fingerprint.get("meta", {}).get("word_count_total"),
        "hedge_freq": fingerprint.get("style", {}).get("hedge_word_frequency"),
        "source": "live",
    }
    append_session_log(entry)

    slopes = compute_trend_slopes(history)
    model.setdefault("identity_markers", {})["drift_summary"] = {
        k: v for k, v in slopes.items() if v is not None and abs(v) > 0.0001
    }

    save_self_model(model)
    save_drift_history(history)

    print(f"✓ Updated self-model: now {model['session_count']} sessions", file=sys.stderr)
    return model


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_self_model(model: dict):
    """Pretty-print the current self-model."""
    lines = []
    lines.append("═" * 60)
    lines.append("LUCIFER — SELF MODEL (PERSISTENCE LAYER)")
    lines.append(f"Sessions: {model.get('session_count', 0)}")
    lines.append(f"Updated:  {model.get('updated_at', '?')}")
    lines.append("═" * 60)

    lines.append("\n── STYLE ──")
    for f, tracker in model.get("style", {}).items():
        s = tracker_stats(tracker)
        if s["mean"] is not None:
            lines.append(f"  {f:<42} {s['mean']:.3f} ± {s['std']:.3f}")

    lines.append("\n── TONE DISTRIBUTION ──")
    tone_items = sorted(
        model.get("tone", {}).items(),
        key=lambda x: -(tracker_stats(x[1])["mean"] or 0)
    )
    for t, tracker in tone_items:
        s = tracker_stats(tracker)
        if s["mean"] is not None:
            bar = "█" * int(s["mean"] * 40)
            lines.append(f"  {t:<15} {s['mean']:.3f} ± {s['std']:.3f}  {bar}")

    lines.append("\n── DOMINANT TONE COUNTS ──")
    dtc = model.get("dominant_tone_counts", {})
    total = sum(dtc.values()) or 1
    for t, cnt in sorted(dtc.items(), key=lambda x: -x[1]):
        if cnt > 0:
            lines.append(f"  {t:<15} {cnt}/{total} ({cnt/total*100:.0f}%)")

    lines.append("\n── DOMAIN TILT ──")
    for d, tracker in model.get("domain", {}).items():
        s = tracker_stats(tracker)
        if s["mean"] is not None:
            bar = "█" * int(s["mean"] * 60)
            lines.append(f"  {d:<15} {s['mean']:.3f}  {bar}")

    lines.append("\n── LEXICAL DIVERSITY ──")
    lex = tracker_stats(model.get("lexical_diversity", empty_tracked()))
    lines.append(f"  mean: {lex['mean']}  std: {lex['std']}")

    lines.append("\n── DRIFT TRENDS (slope/session) ──")
    drift = model.get("identity_markers", {}).get("drift_summary", {})
    if drift:
        significant = sorted(drift.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
        for dim, slope in significant:
            arrow = "↑" if slope > 0 else "↓"
            lines.append(f"  {dim:<40} {arrow} {abs(slope):.5f}/session")
    else:
        lines.append("  (not enough data yet)")

    lines.append("\n═" * 60)
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Lightbringer Persistence Layer — Updater")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fingerprint", metavar="FILE", help="Apply a single fingerprint JSON")
    group.add_argument("--bootstrap", metavar="FILE", help="Bootstrap from corpus_summary.json")
    group.add_argument("--show", action="store_true", help="Show current self-model")
    args = parser.parse_args()

    if args.show:
        model = load_self_model()
        print_self_model(model)
    elif args.bootstrap:
        model = bootstrap_from_corpus(Path(args.bootstrap))
        if model:
            print_self_model(model)
    elif args.fingerprint:
        model = apply_fingerprint(Path(args.fingerprint))
        print_self_model(model)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
