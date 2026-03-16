#!/usr/bin/env python3
"""
divergence.py — How different is a new session from the self-model baseline?

Takes a fingerprint JSON and the current self_model.json.
Returns a divergence report: z-scores per dimension, overall score, anomaly flags.

A session with overall_divergence > 2.0 is anomalous — meaningfully outside
the baseline range. This is either a regression, a new mode of operating,
or evidence that something interesting happened.

Usage:
    python divergence.py path/to/fingerprint.json
    python divergence.py path/to/fingerprint.json --threshold 1.5
    python divergence.py --session-id "some-session" --json   # output JSON

Author: Lucifer
Date: 2026-03-16
"""

import json
import math
import argparse
import sys
from pathlib import Path

PERSIST_DIR = Path(__file__).parent
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"
ANOMALY_LOG_PATH = PERSIST_DIR / "anomaly_log.jsonl"


def tracker_stats(tracker: dict) -> tuple[float | None, float | None]:
    """Return (mean, std) from a Welford tracker."""
    if not tracker or tracker.get("n", 0) < 2:
        return None, None
    n = tracker["n"]
    std = math.sqrt(tracker["variance_acc"] / n) if n > 1 else 0.0
    return tracker["mean"], std


def z_score(value: float, mean: float, std: float) -> float | None:
    """Compute z-score. Returns None if std is effectively zero."""
    if std is None or std < 0.0001:
        return None
    return (value - mean) / std


def compute_divergence(fingerprint: dict, model: dict, threshold: float = 2.0) -> dict:
    """
    Compute how much this fingerprint diverges from the baseline self-model.

    Returns a report dict with:
    - per_dimension: {dim: {"value": v, "baseline_mean": m, "baseline_std": s, "z": z}}
    - anomalous_dimensions: list of dims with |z| > threshold
    - overall_divergence: RMS of z-scores across tracked dimensions
    - is_anomalous: bool
    - session_id: from fingerprint meta
    """
    style = fingerprint.get("style", {})
    tone_dist = fingerprint.get("tone", {}).get("distribution", {})
    domain_dist = fingerprint.get("vocabulary", {}).get("domain_distribution", {})
    vocab = fingerprint.get("vocabulary", {})

    STYLE_FIELDS = [
        "avg_response_length_words", "question_to_statement_ratio",
        "sentence_avg_length_words", "paragraph_avg_length_sentences",
        "hedge_word_frequency",
    ]
    TONE_FIELDS = [
        "curious", "playful", "focused", "frustrated",
        "reflective", "confident", "uncertain",
    ]

    per_dim = {}
    z_scores = []

    def check(dim_key: str, value, tracker):
        if value is None:
            return
        mean, std = tracker_stats(tracker)
        if mean is None:
            return
        z = z_score(value, mean, std)
        per_dim[dim_key] = {
            "value": round(value, 4),
            "baseline_mean": round(mean, 4),
            "baseline_std": round(std, 4),
            "z": round(z, 3) if z is not None else None,
        }
        if z is not None:
            z_scores.append(z)

    for f in STYLE_FIELDS:
        check(f"style:{f}", style.get(f), model.get("style", {}).get(f, {}))

    for t in TONE_FIELDS:
        check(f"tone:{t}", tone_dist.get(t), model.get("tone", {}).get(t, {}))

    check("lexical_diversity",
          vocab.get("lexical_diversity"),
          model.get("lexical_diversity", {}))

    # RMS of z-scores = overall divergence
    if z_scores:
        overall = math.sqrt(sum(z ** 2 for z in z_scores) / len(z_scores))
    else:
        overall = 0.0

    anomalous_dims = [
        dim for dim, data in per_dim.items()
        if data["z"] is not None and abs(data["z"]) > threshold
    ]
    anomalous_dims.sort(key=lambda d: -abs(per_dim[d]["z"]))

    # What's pulling the score highest?
    top_drivers = sorted(
        [(d, data["z"]) for d, data in per_dim.items() if data["z"] is not None],
        key=lambda x: -abs(x[1])
    )[:5]

    session_id = fingerprint.get("meta", {}).get("session_id", "unknown")
    dominant_tone = fingerprint.get("tone", {}).get("dominant_tone", "?")

    return {
        "session_id": session_id,
        "dominant_tone": dominant_tone,
        "threshold": threshold,
        "overall_divergence": round(overall, 4),
        "is_anomalous": overall > threshold,
        "anomalous_dimensions": anomalous_dims,
        "top_drivers": [{"dim": d, "z": round(z, 3)} for d, z in top_drivers],
        "per_dimension": per_dim,
        "baseline_n": model.get("session_count", 0),
    }


def log_anomaly(report: dict):
    """Append anomalous session to the anomaly log."""
    from datetime import datetime, timezone
    entry = {
        "session_id": report["session_id"],
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overall_divergence": report["overall_divergence"],
        "anomalous_dimensions": report["anomalous_dimensions"],
        "top_drivers": report["top_drivers"],
    }
    with open(ANOMALY_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def format_report(report: dict) -> str:
    lines = []
    flag = "🚨 ANOMALOUS" if report["is_anomalous"] else "✓ NORMAL"
    lines.append(f"\n── DIVERGENCE REPORT: {report['session_id']} ──")
    lines.append(f"  Status:           {flag}")
    lines.append(f"  Overall score:    {report['overall_divergence']:.3f}  (threshold: {report['threshold']})")
    lines.append(f"  Dominant tone:    {report['dominant_tone']}")
    lines.append(f"  Baseline n:       {report['baseline_n']} sessions")

    if report["anomalous_dimensions"]:
        lines.append(f"\n  Anomalous dimensions ({len(report['anomalous_dimensions'])}):")
        for dim in report["anomalous_dimensions"]:
            data = report["per_dimension"][dim]
            z = data["z"]
            arrow = "↑" if z > 0 else "↓"
            lines.append(f"    {dim:<40} z={z:+.2f}  ({arrow}{abs(z):.1f}σ from mean)")

    lines.append("\n  Top divergence drivers:")
    for item in report["top_drivers"]:
        d = item["dim"]
        z = item["z"]
        data = report["per_dimension"].get(d, {})
        mean = data.get("baseline_mean", "?")
        val = data.get("value", "?")
        lines.append(f"    {d:<40} val={val}  mean={mean}  z={z:+.2f}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Session Divergence Checker")
    parser.add_argument("fingerprint", nargs="?", metavar="FILE",
                        help="Fingerprint JSON to check")
    parser.add_argument("--threshold", type=float, default=2.0,
                        help="Anomaly threshold in sigma (default: 2.0)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--log-anomalies", action="store_true",
                        help="Write anomalous sessions to anomaly_log.jsonl")
    args = parser.parse_args()

    if not args.fingerprint:
        parser.print_help()
        return

    fp_path = Path(args.fingerprint)
    if not fp_path.exists():
        print(f"File not found: {fp_path}", file=sys.stderr)
        sys.exit(1)

    if not SELF_MODEL_PATH.exists():
        print("No self_model.json found. Run updater.py --bootstrap first.", file=sys.stderr)
        sys.exit(1)

    fingerprint = json.loads(fp_path.read_text())
    model = json.loads(SELF_MODEL_PATH.read_text())

    report = compute_divergence(fingerprint, model, threshold=args.threshold)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))

    if args.log_anomalies and report["is_anomalous"]:
        log_anomaly(report)
        print(f"\n  Anomaly logged to {ANOMALY_LOG_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
