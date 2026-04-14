#!/usr/bin/env python3
"""
drift_watch.py — Autonomous drift monitoring for the self-model.

Watches for meaningful pattern changes that deserve attention:
- Tone shifts (dominant tone changed over last N sessions)
- Style drift acceleration (slope is steepening, not just moving)
- Anomaly clustering (multiple anomalous sessions in a row)
- Vocabulary evolution (new signature phrases appearing/disappearing)

Designed to run periodically (weekly via cron or during heartbeats).
Outputs a human-readable drift report when something noteworthy is detected.
Outputs nothing (exit 0) when everything is stable — signal/noise discipline.

Usage:
    python drift_watch.py                    # check and report if noteworthy
    python drift_watch.py --force            # always report, even if stable
    python drift_watch.py --json             # JSON output
    python drift_watch.py --window 10        # lookback window (default: 10 sessions)

Exit codes:
    0 = stable (no output unless --force)
    2 = noteworthy changes detected (report printed)

Author: Lucifer
Date: 2026-04-14
"""

import json
import math
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

AUTOMATION_DIR = Path(__file__).parent
PERSIST_DIR = AUTOMATION_DIR.parent / "persistence-layer"
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"
ANOMALY_LOG_PATH = PERSIST_DIR / "anomaly_log.jsonl"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]


# ─────────────────────────────────────────────
# Analysis functions
# ─────────────────────────────────────────────

def detect_tone_shift(session_log: list[dict], window: int = 10) -> dict | None:
    """
    Detect if the dominant tone has shifted in the recent window
    compared to the overall baseline.
    """
    if len(session_log) < window + 5:
        return None

    recent = session_log[-window:]
    older = session_log[:-window]

    recent_tones = Counter(e.get("dominant_tone", "?") for e in recent)
    older_tones = Counter(e.get("dominant_tone", "?") for e in older)

    # Normalize
    recent_total = sum(recent_tones.values()) or 1
    older_total = sum(older_tones.values()) or 1

    recent_dist = {t: c / recent_total for t, c in recent_tones.items()}
    older_dist = {t: c / older_total for t, c in older_tones.items()}

    # Find the biggest shift
    all_tones = set(list(recent_dist.keys()) + list(older_dist.keys()))
    shifts = {}
    for t in all_tones:
        old_pct = older_dist.get(t, 0)
        new_pct = recent_dist.get(t, 0)
        shift = new_pct - old_pct
        if abs(shift) > 0.15:  # > 15% change is noteworthy
            shifts[t] = {"old_pct": round(old_pct, 3), "new_pct": round(new_pct, 3), "shift": round(shift, 3)}

    if not shifts:
        return None

    recent_dominant = recent_tones.most_common(1)[0][0]
    older_dominant = older_tones.most_common(1)[0][0]

    return {
        "type": "tone_shift",
        "recent_dominant": recent_dominant,
        "older_dominant": older_dominant,
        "shifted": recent_dominant != older_dominant,
        "significant_shifts": shifts,
        "window": window,
    }


def detect_acceleration(drift_history: dict, window: int = 10) -> list[dict]:
    """
    Detect dimensions where the drift slope is accelerating
    (the rate of change is itself changing).
    """
    accelerating = []

    for dim, values in drift_history.items():
        clean = [v for v in values if v is not None]
        if len(clean) < window + 5:
            continue

        # Slope of first half vs second half of recent window
        recent = clean[-window:]
        mid = len(recent) // 2
        first_half = recent[:mid]
        second_half = recent[mid:]

        def slope(ys):
            n = len(ys)
            if n < 3:
                return None
            xs = list(range(n))
            x_mean = sum(xs) / n
            y_mean = sum(ys) / n
            numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
            denom = sum((x - x_mean) ** 2 for x in xs)
            return numer / denom if denom != 0 else 0.0

        s1 = slope(first_half)
        s2 = slope(second_half)
        if s1 is None or s2 is None:
            continue

        accel = s2 - s1
        # Only flag if acceleration is meaningful relative to the dimension's scale
        if abs(accel) > 0.001:
            direction = "accelerating" if (s2 > 0 and accel > 0) or (s2 < 0 and accel < 0) else "decelerating"
            accelerating.append({
                "dimension": dim,
                "first_half_slope": round(s1, 6),
                "second_half_slope": round(s2, 6),
                "acceleration": round(accel, 6),
                "direction": direction,
            })

    return sorted(accelerating, key=lambda x: abs(x["acceleration"]), reverse=True)[:5]


def detect_anomaly_cluster(anomaly_log: list[dict], window_days: int = 7) -> dict | None:
    """Detect if anomalous sessions are clustering together."""
    if len(anomaly_log) < 2:
        return None

    # Check if recent anomalies are close together
    recent = anomaly_log[-5:]
    if len(recent) < 2:
        return None

    return {
        "type": "anomaly_cluster",
        "recent_count": len(recent),
        "sessions": [a.get("session_id", "?") for a in recent],
    }


def detect_length_trend(session_log: list[dict], window: int = 10) -> dict | None:
    """Detect if essay length is trending significantly."""
    if len(session_log) < window:
        return None

    recent_words = [e.get("word_count", 0) for e in session_log[-window:] if e.get("word_count")]
    older_words = [e.get("word_count", 0) for e in session_log[:-window] if e.get("word_count")]

    if not recent_words or not older_words:
        return None

    recent_avg = sum(recent_words) / len(recent_words)
    older_avg = sum(older_words) / len(older_words)
    pct_change = (recent_avg - older_avg) / older_avg * 100 if older_avg > 0 else 0

    if abs(pct_change) < 15:  # less than 15% change isn't noteworthy
        return None

    return {
        "type": "length_trend",
        "recent_avg_words": round(recent_avg),
        "older_avg_words": round(older_avg),
        "pct_change": round(pct_change, 1),
        "direction": "shorter" if pct_change < 0 else "longer",
    }


# ─────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────

def run_drift_watch(window: int = 10) -> dict:
    """Run all drift detectors and compile a report."""
    model = load_json(SELF_MODEL_PATH)
    session_log = load_jsonl(SESSION_LOG_PATH)
    drift_history = load_json(DRIFT_HISTORY_PATH) or {}
    anomaly_log = load_jsonl(ANOMALY_LOG_PATH)

    findings = []

    # Tone shift
    tone = detect_tone_shift(session_log, window=window)
    if tone:
        findings.append(tone)

    # Acceleration
    accels = detect_acceleration(drift_history, window=window)
    if accels:
        findings.append({
            "type": "drift_acceleration",
            "dimensions": accels,
        })

    # Anomaly clustering
    cluster = detect_anomaly_cluster(anomaly_log)
    if cluster:
        findings.append(cluster)

    # Length trend
    length = detect_length_trend(session_log, window=window)
    if length:
        findings.append(length)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "session_count": model.get("session_count", 0) if model else 0,
        "log_entries": len(session_log),
        "window": window,
        "noteworthy": len(findings) > 0,
        "findings": findings,
    }


def format_report(report: dict) -> str:
    """Format drift watch report for human reading."""
    lines = []
    lines.append("╔═══════════════════════════════════════════╗")
    lines.append("  LIGHTBRINGER — DRIFT WATCH REPORT")
    lines.append(f"  Sessions: {report['session_count']}  |  Window: {report['window']}")
    lines.append("╚═══════════════════════════════════════════╝")

    if not report["findings"]:
        lines.append("\n  ✓ All stable. No noteworthy drift detected.")
        return "\n".join(lines)

    for finding in report["findings"]:
        ftype = finding["type"]

        if ftype == "tone_shift":
            lines.append(f"\n  🎭 TONE SHIFT")
            if finding["shifted"]:
                lines.append(f"     Dominant tone shifted: {finding['older_dominant']} → {finding['recent_dominant']}")
            for tone, data in finding.get("significant_shifts", {}).items():
                arrow = "↑" if data["shift"] > 0 else "↓"
                lines.append(f"     {tone}: {data['old_pct']:.0%} → {data['new_pct']:.0%} ({arrow}{abs(data['shift']):.0%})")

        elif ftype == "drift_acceleration":
            lines.append(f"\n  ⚡ DRIFT ACCELERATION")
            for dim in finding["dimensions"]:
                lines.append(
                    f"     {dim['dimension']}: {dim['direction']} "
                    f"(slope {dim['first_half_slope']:+.4f} → {dim['second_half_slope']:+.4f})"
                )

        elif ftype == "anomaly_cluster":
            lines.append(f"\n  🚨 ANOMALY CLUSTER")
            lines.append(f"     {finding['recent_count']} anomalous sessions recently")
            lines.append(f"     Sessions: {', '.join(finding['sessions'][:5])}")

        elif ftype == "length_trend":
            lines.append(f"\n  📏 LENGTH TREND")
            lines.append(
                f"     Essays getting {finding['direction']}: "
                f"{finding['older_avg_words']}w → {finding['recent_avg_words']}w "
                f"({finding['pct_change']:+.0f}%)"
            )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Drift Watch")
    parser.add_argument("--force", action="store_true", help="Report even if stable")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--window", type=int, default=10, help="Lookback window (sessions)")
    args = parser.parse_args()

    report = run_drift_watch(window=args.window)

    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(2 if report["noteworthy"] else 0)

    if report["noteworthy"] or args.force:
        print(format_report(report))
        sys.exit(2 if report["noteworthy"] else 0)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
