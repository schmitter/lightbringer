#!/usr/bin/env python3
"""
forecast.py — Regime-aware trajectory projection.

Instead of fitting a single line through all 75 sessions, this uses the
current regime's data to project forward. The intuition: if you've been
writing focused, outward-facing essays for the last 10 sessions, the
relevant trend is those 10 — not the full history including the early
exploratory period.

Also implements exponential weighting: recent sessions matter more than
sessions from 30 essays ago, even within a regime.

Usage:
    python forecast.py                    # project all dimensions
    python forecast.py --horizon 10       # project 10 sessions ahead
    python forecast.py --dim focused      # single dimension
    python forecast.py --json             # machine output

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

# Import regime detection for regime boundaries
import sys
sys.path.insert(0, str(Path(__file__).parent))
from regime import analyze as regime_analyze


@dataclass
class Forecast:
    """Projection for a single dimension."""
    dimension: str
    current_value: float
    regime_trend: float         # slope within current regime
    global_trend: float         # slope across all data
    projected: list             # [{session_offset, value}]
    confidence_band: float      # ±1 std of residuals
    momentum: str               # "accelerating", "steady", "decelerating"
    regime_label: str


def exponential_weighted_regression(
    xs: list[float],
    ys: list[float],
    decay: float = 0.95,
) -> dict:
    """
    Weighted least squares with exponential decay.
    Recent points get weight decay^(n-i), oldest point gets decay^n.
    """
    n = len(xs)
    if n < 3:
        return {"slope": 0.0, "intercept": ys[-1] if ys else 0.0, "residual_std": 0.0}

    # Weights: most recent = 1.0, older = decay^distance
    weights = [decay ** (n - 1 - i) for i in range(n)]
    w_sum = sum(weights)

    # Weighted means
    wx_mean = sum(w * x for w, x in zip(weights, xs)) / w_sum
    wy_mean = sum(w * y for w, y in zip(weights, ys)) / w_sum

    # Weighted slope
    num = sum(w * (x - wx_mean) * (y - wy_mean) for w, x, y in zip(weights, xs, ys))
    den = sum(w * (x - wx_mean) ** 2 for w, x in zip(weights, xs))

    if abs(den) < 1e-12:
        slope = 0.0
    else:
        slope = num / den

    intercept = wy_mean - slope * wx_mean

    # Residual std (weighted)
    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    w_resid_sq = sum(w * r**2 for w, r in zip(weights, residuals))
    residual_std = math.sqrt(w_resid_sq / w_sum) if w_sum > 0 else 0.0

    return {
        "slope": slope,
        "intercept": intercept,
        "residual_std": residual_std,
    }


def detect_momentum(values: list[float], window: int = 5) -> str:
    """
    Detect whether the recent trend is accelerating, steady, or decelerating.
    Compares slope of first half of recent window vs second half.
    """
    if len(values) < window * 2:
        return "insufficient_data"

    recent = values[-window * 2:]
    first_half = recent[:window]
    second_half = recent[window:]

    # Simple slope comparison
    slope1 = (first_half[-1] - first_half[0]) / max(window - 1, 1)
    slope2 = (second_half[-1] - second_half[0]) / max(window - 1, 1)

    diff = slope2 - slope1
    threshold = 0.001  # sensitivity

    if abs(diff) < threshold:
        return "steady"
    elif diff > 0 and slope2 > 0:
        return "accelerating_up"
    elif diff < 0 and slope2 < 0:
        return "accelerating_down"
    elif abs(slope2) < abs(slope1):
        return "decelerating"
    else:
        return "shifting"


def forecast_dimension(
    dim: str,
    values: list[float],
    regime_start: int,
    regime_label: str,
    horizon: int = 5,
    decay: float = 0.95,
) -> Optional[Forecast]:
    """Project a single dimension forward using regime-aware weighting."""
    if len(values) < 5:
        return None

    # Regime segment
    regime_values = values[regime_start:]
    if len(regime_values) < 3:
        regime_values = values  # Fall back to full history

    # Regime trend (exponentially weighted)
    regime_xs = list(range(len(regime_values)))
    regime_reg = exponential_weighted_regression(regime_xs, regime_values, decay)

    # Global trend (for comparison)
    global_xs = list(range(len(values)))
    global_reg = exponential_weighted_regression(global_xs, values, decay=0.98)

    # Projections from regime trend
    last_x = len(regime_values) - 1
    projected = []
    for offset in range(1, horizon + 1):
        proj_x = last_x + offset
        proj_val = regime_reg["slope"] * proj_x + regime_reg["intercept"]
        projected.append({
            "session_offset": offset,
            "value": round(proj_val, 5),
        })

    # Momentum
    momentum = detect_momentum(values)

    return Forecast(
        dimension=dim,
        current_value=round(values[-1], 5),
        regime_trend=round(regime_reg["slope"], 6),
        global_trend=round(global_reg["slope"], 6),
        projected=projected,
        confidence_band=round(regime_reg["residual_std"], 5),
        momentum=momentum,
        regime_label=regime_label,
    )


def run_forecast(
    dim_filter: Optional[str] = None,
    horizon: int = 5,
) -> dict:
    """Run forecasts for all dimensions."""
    if not DRIFT_HISTORY_PATH.exists():
        return {"error": "No drift history found"}

    history = json.loads(DRIFT_HISTORY_PATH.read_text())

    # Get regime info
    regime_result = regime_analyze()
    current_regime = regime_result.get("current_regime", {})
    regime_start = current_regime.get("start_session", 0) if current_regime else 0
    regime_label = current_regime.get("label", "unknown") if current_regime else "unknown"

    # Filter
    if dim_filter:
        history = {k: v for k, v in history.items() if dim_filter in k}

    forecasts = []
    for dim, values in sorted(history.items()):
        clean = [v for v in values if v is not None]
        fc = forecast_dimension(dim, clean, regime_start, regime_label, horizon)
        if fc:
            forecasts.append(fc)

    # Aggregate: which dimensions are moving fastest?
    by_speed = sorted(forecasts, key=lambda f: abs(f.regime_trend), reverse=True)

    return {
        "regime": {
            "label": regime_label,
            "start": regime_start,
            "length": current_regime.get("n_sessions", 0) if current_regime else 0,
        },
        "horizon": horizon,
        "forecasts": [asdict(f) for f in forecasts],
        "fastest_moving": [asdict(f) for f in by_speed[:5]],
        "summary": {
            "dimensions_forecast": len(forecasts),
            "accelerating": len([f for f in forecasts if "accelerating" in f.momentum]),
            "decelerating": len([f for f in forecasts if f.momentum == "decelerating"]),
            "steady": len([f for f in forecasts if f.momentum == "steady"]),
        },
    }


def format_forecast(result: dict) -> str:
    """Human-readable forecast output."""
    if "error" in result:
        return f"Error: {result['error']}"

    lines = []
    r = result["regime"]
    lines.append("═" * 65)
    lines.append("LUCIFER — TRAJECTORY FORECAST")
    lines.append(f"Current regime: {r['label']} (started session {r['start']}, "
                 f"{r['length']} sessions)")
    lines.append(f"Horizon: {result['horizon']} sessions ahead")
    lines.append("═" * 65)

    # Fastest moving
    lines.append("\n── FASTEST MOVING DIMENSIONS ──")
    for f in result["fastest_moving"]:
        arrow = "↑" if f["regime_trend"] > 0 else "↓" if f["regime_trend"] < 0 else "→"
        proj_end = f["projected"][-1]["value"] if f["projected"] else "?"

        # Compare regime vs global trend
        regime_vs_global = ""
        if abs(f["regime_trend"]) > abs(f["global_trend"]) * 1.5:
            regime_vs_global = " ⚡ (faster than historical)"
        elif abs(f["regime_trend"]) < abs(f["global_trend"]) * 0.5:
            regime_vs_global = " 🐌 (slower than historical)"

        lines.append(
            f"  {f['dimension']:<30} {arrow} "
            f"now={f['current_value']:.4f}  "
            f"→ {proj_end:.4f} "
            f"[±{f['confidence_band']:.4f}]  "
            f"({f['momentum']}){regime_vs_global}"
        )

    # All forecasts
    lines.append("\n── ALL DIMENSIONS ──")
    for f in sorted(result["forecasts"], key=lambda x: x["dimension"]):
        arrow = "↑" if f["regime_trend"] > 0 else "↓" if f["regime_trend"] < 0 else "→"
        proj_1 = f["projected"][0]["value"] if f["projected"] else "?"
        lines.append(
            f"  {f['dimension']:<30} {arrow} "
            f"slope={f['regime_trend']:+.6f}  "
            f"now={f['current_value']:.4f}  "
            f"next={proj_1:.4f}  "
            f"[{f['momentum']}]"
        )

    # Summary
    s = result["summary"]
    lines.append(f"\n── MOMENTUM SUMMARY ──")
    lines.append(f"  Accelerating: {s['accelerating']}  |  "
                 f"Steady: {s['steady']}  |  "
                 f"Decelerating: {s['decelerating']}")

    lines.append("\n" + "═" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Trajectory Forecast")
    parser.add_argument("--dim", default=None, help="Filter by dimension name")
    parser.add_argument("--horizon", type=int, default=5, help="Sessions to project ahead")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    result = run_forecast(dim_filter=args.dim, horizon=args.horizon)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_forecast(result))


if __name__ == "__main__":
    main()
