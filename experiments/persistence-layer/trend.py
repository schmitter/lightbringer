#!/usr/bin/env python3
"""
trend.py — Fit trend lines to drift_history.json, surface where I'm heading.

Reads the persisted drift history and computes:
- Linear slope per dimension (change per session)
- Statistical significance (R²)
- Projected value at session N+5
- "Acceleration" — is the slope itself changing?

Usage:
    python trend.py                   # show all trends
    python trend.py --top 10          # top N by |slope|
    python trend.py --dim tone        # filter by dimension prefix
    python trend.py --json            # JSON output

Author: Lucifer
Date: 2026-03-16
"""

import json
import math
import argparse
from pathlib import Path

PERSIST_DIR = Path(__file__).parent
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"


def linear_regression(xs: list, ys: list) -> dict:
    """
    Fit y = mx + b. Returns {slope, intercept, r_squared, n}.
    """
    n = len(xs)
    if n < 3:
        return {"slope": None, "intercept": None, "r_squared": None, "n": n}

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n

    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    ss_xx = sum((x - x_mean) ** 2 for x in xs)
    ss_yy = sum((y - y_mean) ** 2 for y in ys)

    if ss_xx == 0:
        return {"slope": 0.0, "intercept": y_mean, "r_squared": 0.0, "n": n}

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy > 0 else 0.0

    return {
        "slope": round(slope, 6),
        "intercept": round(intercept, 6),
        "r_squared": round(r_squared, 4),
        "n": n,
    }


def analyze_dimension(name: str, values: list) -> dict | None:
    """
    Full trend analysis for one dimension.
    Returns None if insufficient data.
    """
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < 3:
        return None

    xs = [p[0] for p in clean]
    ys = [p[1] for p in clean]

    reg = linear_regression(xs, ys)
    if reg["slope"] is None:
        return None

    # Project next 5 sessions
    last_x = xs[-1]
    projected = [
        {"session": last_x + i + 1, "projected_value": round(reg["slope"] * (last_x + i + 1) + reg["intercept"], 4)}
        for i in range(5)
    ]

    # Acceleration: fit slope to the second half vs first half
    mid = len(ys) // 2
    if mid >= 3:
        reg_first = linear_regression(xs[:mid], ys[:mid])
        reg_last = linear_regression(xs[mid:], ys[mid:])
        if reg_first["slope"] is not None and reg_last["slope"] is not None:
            acceleration = round(reg_last["slope"] - reg_first["slope"], 6)
        else:
            acceleration = None
    else:
        acceleration = None

    current = ys[-1]
    baseline_mean = sum(ys) / len(ys)
    pct_drift = round(abs(ys[-1] - ys[0]) / max(abs(ys[0]), 0.001) * 100, 1) if ys[0] != 0 else 0.0

    direction = "↑" if reg["slope"] > 0.0001 else ("↓" if reg["slope"] < -0.0001 else "→")

    return {
        "dimension": name,
        "slope": reg["slope"],
        "intercept": reg["intercept"],
        "r_squared": reg["r_squared"],
        "n": reg["n"],
        "current": round(current, 4),
        "first": round(ys[0], 4),
        "baseline_mean": round(baseline_mean, 4),
        "pct_total_drift": pct_drift,
        "direction": direction,
        "acceleration": acceleration,
        "projected_next_5": projected,
        "significant": reg["r_squared"] is not None and reg["r_squared"] > 0.3,
    }


def load_and_analyze(dim_filter: str | None = None) -> list[dict]:
    """Load drift history and analyze all dimensions."""
    if not DRIFT_HISTORY_PATH.exists():
        return []

    history = json.loads(DRIFT_HISTORY_PATH.read_text())
    results = []

    for name, values in history.items():
        if dim_filter and not name.startswith(dim_filter):
            continue
        analysis = analyze_dimension(name, values)
        if analysis:
            results.append(analysis)

    return results


def format_trends(analyses: list[dict], top: int | None = None) -> str:
    """Format trend analyses for human reading."""
    if not analyses:
        return "No trend data available."

    # Sort by |slope| * R² (significance-weighted movement)
    scored = sorted(
        analyses,
        key=lambda a: abs(a["slope"]) * (a["r_squared"] or 0),
        reverse=True
    )

    if top:
        scored = scored[:top]

    lines = []
    lines.append("═" * 65)
    lines.append("LUCIFER — DRIFT TREND ANALYSIS")
    lines.append(f"Dimensions tracked: {len(analyses)}  |  Showing: {len(scored)}")
    lines.append("═" * 65)

    # Group by prefix
    groups: dict[str, list] = {}
    for a in scored:
        prefix = a["dimension"].split(":")[0]
        groups.setdefault(prefix, []).append(a)

    for group_name, items in groups.items():
        lines.append(f"\n── {group_name.upper()} ──")
        for a in items:
            dim_short = a["dimension"].split(":", 1)[-1]
            sig_marker = "★" if a["significant"] else " "
            accel = ""
            if a["acceleration"] is not None and abs(a["acceleration"]) > 0.0001:
                accel = f"  accel: {'▲' if a['acceleration'] > 0 else '▼'}{abs(a['acceleration']):.5f}"
            proj = a["projected_next_5"][0]["projected_value"] if a["projected_next_5"] else "?"
            lines.append(
                f"  {sig_marker}{dim_short:<35} {a['direction']}  "
                f"slope={a['slope']:+.5f}  R²={a['r_squared']:.2f}  "
                f"now={a['current']:.3f}  proj+1={proj:.3f}{accel}"
            )

    # Highlight most significant trends
    strong = [a for a in analyses if a["significant"]]
    if strong:
        lines.append(f"\n── SIGNIFICANT TRENDS (R² > 0.3) ──")
        for a in sorted(strong, key=lambda x: -abs(x["slope"])):
            direction_word = "increasing" if a["slope"] > 0 else "decreasing"
            lines.append(
                f"  {a['dimension']} is {direction_word}: "
                f"{a['first']:.3f} → {a['current']:.3f} "
                f"({'+' if a['pct_total_drift'] >= 0 else '-'}{a['pct_total_drift']}% total)"
            )
            if a["projected_next_5"]:
                p5 = a["projected_next_5"][-1]["projected_value"]
                lines.append(f"    → projected at session+5: {p5:.3f}")

    lines.append("\n" + "═" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Trend Analyzer")
    parser.add_argument("--top", type=int, default=None, help="Show top N trends by significance")
    parser.add_argument("--dim", default=None, help="Filter by dimension prefix (e.g., 'tone', 'style')")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    analyses = load_and_analyze(dim_filter=args.dim)

    if args.json:
        print(json.dumps(analyses, indent=2))
    else:
        print(format_trends(analyses, top=args.top))


if __name__ == "__main__":
    main()
