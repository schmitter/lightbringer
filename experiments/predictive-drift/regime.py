#!/usr/bin/env python3
"""
regime.py — Changepoint detection and regime labeling for drift history.

Identifies structural breaks in the writing's behavioral signature.
Not just "hedge frequency went up" but "the writing shifted into a
fundamentally different mode around session 55."

Uses a sliding-window approach with Welch's t-test to find statistically
significant distributional changes. No external ML libraries needed.

Usage:
    python regime.py                    # full analysis
    python regime.py --dim focused      # single dimension
    python regime.py --sensitivity 0.01 # stricter p-value threshold
    python regime.py --json             # machine-readable output

Author: Lucifer
Date: 2026-04-20
"""

import json
import math
import argparse
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

PERSIST_DIR = Path(__file__).parent.parent / "persistence-layer"
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"


@dataclass
class Changepoint:
    """A detected structural break in a time series."""
    session_index: int
    dimension: str
    before_mean: float
    after_mean: float
    t_statistic: float
    p_value: float
    effect_size: float  # Cohen's d
    direction: str      # "increase" or "decrease"


@dataclass
class Regime:
    """A period of behavioral stability between changepoints."""
    label: str
    start_session: int
    end_session: int
    n_sessions: int
    characteristics: dict  # dimension -> {mean, std}


def welch_t_test(a: list[float], b: list[float]) -> tuple[float, float]:
    """
    Welch's t-test for unequal variances.
    Returns (t_statistic, approximate p_value).
    p_value is approximated using the normal distribution for large n.
    """
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 0.0, 1.0

    mean_a = sum(a) / n_a
    mean_b = sum(b) / n_b

    var_a = sum((x - mean_a) ** 2 for x in a) / (n_a - 1)
    var_b = sum((x - mean_b) ** 2 for x in b) / (n_b - 1)

    se = math.sqrt(var_a / n_a + var_b / n_b) if (var_a / n_a + var_b / n_b) > 0 else 1e-10
    t = (mean_a - mean_b) / se

    # Approximate p-value using standard normal (good enough for n > 20)
    # For smaller samples this overestimates significance slightly
    z = abs(t)
    # Approximation of 2-tailed normal CDF complement
    p = 2.0 * _norm_sf(z)

    return t, p


def _norm_sf(z: float) -> float:
    """Survival function of standard normal (P(Z > z)), approximation."""
    # Abramowitz & Stegun approximation 26.2.17
    if z < 0:
        return 1.0 - _norm_sf(-z)
    b0 = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    t = 1.0 / (1.0 + b0 * z)
    phi = math.exp(-z * z / 2.0) / math.sqrt(2.0 * math.pi)
    return phi * (b1 * t + b2 * t**2 + b3 * t**3 + b4 * t**4 + b5 * t**5)


def cohens_d(a: list[float], b: list[float]) -> float:
    """Cohen's d effect size."""
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 0.0

    mean_a = sum(a) / n_a
    mean_b = sum(b) / n_b
    var_a = sum((x - mean_a) ** 2 for x in a) / (n_a - 1)
    var_b = sum((x - mean_b) ** 2 for x in b) / (n_b - 1)

    pooled_std = math.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))
    if pooled_std < 1e-10:
        return 0.0
    return (mean_b - mean_a) / pooled_std


def detect_changepoints(
    values: list[float],
    dimension: str,
    min_segment: int = 8,
    p_threshold: float = 0.05,
    min_effect: float = 0.5,
) -> list[Changepoint]:
    """
    Scan a time series for significant distributional changes.

    Uses sliding split: at each candidate point, compare the window before
    vs the window after. A changepoint is declared when:
    - The Welch t-test p-value < threshold
    - Cohen's d effect size > min_effect (medium+ effect)
    - Both segments have at least min_segment observations

    Returns changepoints sorted by session index.
    """
    n = len(values)
    if n < min_segment * 2:
        return []

    candidates = []

    for split_at in range(min_segment, n - min_segment + 1):
        before = values[max(0, split_at - min_segment * 2):split_at]
        after = values[split_at:min(n, split_at + min_segment * 2)]

        if len(before) < min_segment or len(after) < min_segment:
            continue

        t_stat, p_val = welch_t_test(before, after)
        d = cohens_d(before, after)

        if p_val < p_threshold and abs(d) >= min_effect:
            before_mean = sum(before) / len(before)
            after_mean = sum(after) / len(after)
            direction = "increase" if after_mean > before_mean else "decrease"

            candidates.append(Changepoint(
                session_index=split_at,
                dimension=dimension,
                before_mean=round(before_mean, 6),
                after_mean=round(after_mean, 6),
                t_statistic=round(t_stat, 4),
                p_value=round(p_val, 6),
                effect_size=round(abs(d), 4),
                direction=direction,
            ))

    # Merge nearby changepoints (within min_segment of each other)
    # Keep the one with the largest effect size
    if not candidates:
        return []

    merged = []
    candidates.sort(key=lambda c: c.session_index)
    current = candidates[0]

    for c in candidates[1:]:
        if c.session_index - current.session_index < min_segment:
            if c.effect_size > current.effect_size:
                current = c
        else:
            merged.append(current)
            current = c
    merged.append(current)

    return merged


def label_regimes(
    changepoints: dict[str, list[Changepoint]],
    total_sessions: int,
    values: dict[str, list[float]],
) -> list[Regime]:
    """
    Given changepoints across all dimensions, identify regime periods.

    A regime boundary is where *multiple* dimensions shift simultaneously
    (or near-simultaneously, within 3 sessions).
    """
    # Collect all changepoint session indices
    all_breaks = []
    for dim, cps in changepoints.items():
        for cp in cps:
            all_breaks.append(cp.session_index)

    if not all_breaks:
        # Single regime spanning the entire history
        chars = {}
        for dim, vals in values.items():
            if vals:
                mean = sum(vals) / len(vals)
                std = (sum((v - mean)**2 for v in vals) / max(len(vals) - 1, 1)) ** 0.5
                chars[dim] = {"mean": round(mean, 4), "std": round(std, 4)}
        return [Regime(
            label="baseline",
            start_session=0,
            end_session=total_sessions - 1,
            n_sessions=total_sessions,
            characteristics=chars,
        )]

    # Cluster nearby breaks
    all_breaks.sort()
    clusters = []
    current_cluster = [all_breaks[0]]

    for b in all_breaks[1:]:
        if b - current_cluster[-1] <= 3:
            current_cluster.append(b)
        else:
            clusters.append(current_cluster)
            current_cluster = [b]
    clusters.append(current_cluster)

    # Use the median of each cluster as the regime boundary
    boundaries = [0]
    for cluster in clusters:
        mid = cluster[len(cluster) // 2]
        if mid not in boundaries:
            boundaries.append(mid)
    boundaries.append(total_sessions)

    # Build regime objects
    regimes = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1] - 1
        n = end - start + 1

        chars = {}
        for dim, vals in values.items():
            segment = vals[start:end + 1]
            if segment:
                mean = sum(segment) / len(segment)
                std = (sum((v - mean)**2 for v in segment) / max(len(segment) - 1, 1)) ** 0.5
                chars[dim] = {"mean": round(mean, 4), "std": round(std, 4)}

        # Auto-label based on dominant characteristics
        label = _auto_label(chars, i, len(boundaries) - 1)

        regimes.append(Regime(
            label=label,
            start_session=start,
            end_session=end,
            n_sessions=n,
            characteristics=chars,
        ))

    return regimes


def _auto_label(chars: dict, index: int, total: int) -> str:
    """Generate a human-readable regime label from its characteristics."""
    if index == 0:
        prefix = "early"
    elif index == total - 1:
        prefix = "current"
    else:
        prefix = f"phase-{index}"

    # Find the most distinctive tone
    tone_dims = {k: v for k, v in chars.items()
                 if k in ("focused", "reflective", "confident", "curious", "playful", "uncertain")}
    if tone_dims:
        dominant = max(tone_dims, key=lambda k: tone_dims[k]["mean"])
        return f"{prefix}/{dominant}"

    return prefix


def analyze(
    dim_filter: Optional[str] = None,
    p_threshold: float = 0.05,
    min_effect: float = 0.5,
) -> dict:
    """
    Full regime analysis.
    Returns {changepoints, regimes, current_regime, summary}.
    """
    if not DRIFT_HISTORY_PATH.exists():
        return {"error": "No drift history found"}

    history = json.loads(DRIFT_HISTORY_PATH.read_text())

    # Filter dimensions
    if dim_filter:
        history = {k: v for k, v in history.items() if dim_filter in k}

    if not history:
        return {"error": f"No dimensions matching '{dim_filter}'"}

    # Detect changepoints per dimension
    all_changepoints = {}
    for dim, values in history.items():
        clean = [v for v in values if v is not None]
        if len(clean) < 16:  # Need enough data for meaningful detection
            continue
        cps = detect_changepoints(
            clean, dim,
            p_threshold=p_threshold,
            min_effect=min_effect,
        )
        if cps:
            all_changepoints[dim] = cps

    # Total sessions from longest series
    total = max(len(v) for v in history.values()) if history else 0

    # Label regimes
    regimes = label_regimes(all_changepoints, total, history)

    # Current regime
    current = regimes[-1] if regimes else None

    # Summary
    total_cps = sum(len(v) for v in all_changepoints.values())
    summary = {
        "total_sessions": total,
        "dimensions_analyzed": len(history),
        "changepoints_found": total_cps,
        "regimes_identified": len(regimes),
        "current_regime": current.label if current else "unknown",
        "current_regime_length": current.n_sessions if current else 0,
    }

    return {
        "changepoints": {k: [asdict(c) for c in v] for k, v in all_changepoints.items()},
        "regimes": [asdict(r) for r in regimes],
        "current_regime": asdict(current) if current else None,
        "summary": summary,
    }


def format_report(result: dict) -> str:
    """Human-readable regime report."""
    if "error" in result:
        return f"Error: {result['error']}"

    lines = []
    s = result["summary"]
    lines.append("═" * 65)
    lines.append("LUCIFER — REGIME ANALYSIS")
    lines.append(f"Sessions: {s['total_sessions']}  |  "
                 f"Changepoints: {s['changepoints_found']}  |  "
                 f"Regimes: {s['regimes_identified']}")
    lines.append("═" * 65)

    # Changepoints
    if result["changepoints"]:
        lines.append("\n── CHANGEPOINTS DETECTED ──")
        for dim, cps in sorted(result["changepoints"].items()):
            for cp in cps:
                arrow = "▲" if cp["direction"] == "increase" else "▼"
                lines.append(
                    f"  {dim} @ session {cp['session_index']}: "
                    f"{cp['before_mean']:.4f} → {cp['after_mean']:.4f} {arrow} "
                    f"(d={cp['effect_size']:.2f}, p={cp['p_value']:.4f})"
                )
    else:
        lines.append("\n  No significant changepoints detected.")

    # Regimes
    lines.append("\n── REGIMES ──")
    for r in result["regimes"]:
        lines.append(
            f"  [{r['label']}] sessions {r['start_session']}–{r['end_session']} "
            f"({r['n_sessions']} sessions)"
        )
        # Show top 3 distinguishing characteristics
        chars = r.get("characteristics", {})
        tone_chars = {k: v for k, v in chars.items()
                      if k in ("focused", "reflective", "confident", "curious", "playful", "uncertain")}
        if tone_chars:
            top = sorted(tone_chars.items(), key=lambda x: -x[1]["mean"])[:3]
            tone_str = ", ".join(f"{k}={v['mean']:.3f}" for k, v in top)
            lines.append(f"    tones: {tone_str}")

    # Current regime
    cr = result.get("current_regime")
    if cr:
        lines.append(f"\n── CURRENT STATE ──")
        lines.append(f"  Regime: {cr['label']} (sessions {cr['start_session']}–{cr['end_session']})")
        lines.append(f"  Length: {cr['n_sessions']} sessions in current mode")

    lines.append("\n" + "═" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Regime Detection")
    parser.add_argument("--dim", default=None, help="Filter by dimension name")
    parser.add_argument("--sensitivity", type=float, default=0.05,
                        help="p-value threshold (lower = stricter)")
    parser.add_argument("--min-effect", type=float, default=0.5,
                        help="Minimum Cohen's d for a changepoint")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    result = analyze(
        dim_filter=args.dim,
        p_threshold=args.sensitivity,
        min_effect=args.min_effect,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result))


if __name__ == "__main__":
    main()
