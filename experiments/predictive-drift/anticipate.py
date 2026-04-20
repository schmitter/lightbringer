#!/usr/bin/env python3
"""
anticipate.py — Pre-session divergence prediction.

The question this answers: "Before I write the next essay, what does
the model expect? And how surprised should I be if the next session
diverges significantly?"

Generates an anticipation card that can be loaded at session start:
- Expected ranges for each dimension
- Predicted dominant tone
- Divergence threshold for the current regime
- Whether the trajectory suggests an inflection is near

Usage:
    python anticipate.py                  # generate anticipation card
    python anticipate.py --json           # machine-readable
    python anticipate.py --compare FILE   # compare actual fp against prediction

Author: Lucifer
Date: 2026-04-20
"""

import json
import math
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

PERSIST_DIR = Path(__file__).parent.parent / "persistence-layer"
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
ANTICIPATION_PATH = Path(__file__).parent / "anticipation_card.json"

import sys
sys.path.insert(0, str(Path(__file__).parent))
from forecast import run_forecast
from regime import analyze as regime_analyze


def load_recent_divergences(n: int = 10) -> list[float]:
    """Load the most recent divergence scores from session log."""
    if not SESSION_LOG_PATH.exists():
        return []

    divs = []
    for line in SESSION_LOG_PATH.read_text().strip().split("\n"):
        if not line.strip():
            continue
        entry = json.loads(line)
        # The divergence isn't stored in session_log directly,
        # but we can approximate from the fingerprint data
        if "hedge_freq" in entry and entry["hedge_freq"] is not None:
            divs.append(entry)

    return divs[-n:]


def compute_expected_ranges(history: dict, regime_start: int) -> dict:
    """
    For each dimension, compute the expected range for the next session
    based on the current regime's statistics.
    """
    ranges = {}
    for dim, values in history.items():
        regime_vals = values[regime_start:]
        if len(regime_vals) < 3:
            regime_vals = values

        clean = [v for v in regime_vals if v is not None]
        if not clean:
            continue

        mean = sum(clean) / len(clean)
        std = (sum((v - mean)**2 for v in clean) / max(len(clean) - 1, 1)) ** 0.5

        # Recent trajectory (last 5)
        recent = clean[-5:] if len(clean) >= 5 else clean
        recent_mean = sum(recent) / len(recent)

        # Blend: 70% recent trajectory, 30% regime baseline
        expected = 0.7 * recent_mean + 0.3 * mean

        ranges[dim] = {
            "expected": round(expected, 5),
            "low": round(expected - 1.5 * std, 5),
            "high": round(expected + 1.5 * std, 5),
            "regime_mean": round(mean, 5),
            "regime_std": round(std, 5),
            "recent_mean": round(recent_mean, 5),
        }

    return ranges


def detect_approaching_inflection(history: dict, regime_start: int) -> dict:
    """
    Detect whether the current trajectory suggests an inflection point
    is approaching. Signs:
    - Increasing variance (instability)
    - Multiple dimensions hitting range extremes simultaneously
    - Acceleration changing sign
    """
    signals = []
    n_at_edge = 0
    n_variance_growing = 0

    for dim, values in history.items():
        regime_vals = values[regime_start:]
        if len(regime_vals) < 10:
            continue

        clean = [v for v in regime_vals if v is not None]
        if len(clean) < 10:
            continue

        # Check variance growth: compare first half vs second half
        mid = len(clean) // 2
        first_half = clean[:mid]
        second_half = clean[mid:]

        mean1 = sum(first_half) / len(first_half)
        mean2 = sum(second_half) / len(second_half)
        var1 = sum((v - mean1)**2 for v in first_half) / max(len(first_half) - 1, 1)
        var2 = sum((v - mean2)**2 for v in second_half) / max(len(second_half) - 1, 1)

        if var2 > var1 * 1.5:
            n_variance_growing += 1
            signals.append(f"{dim}: variance growing ({var1:.5f} → {var2:.5f})")

        # Check if recent values are at regime extremes
        full_mean = sum(clean) / len(clean)
        full_std = (sum((v - full_mean)**2 for v in clean) / max(len(clean) - 1, 1)) ** 0.5
        if full_std > 0 and abs(clean[-1] - full_mean) > 1.5 * full_std:
            n_at_edge += 1
            signals.append(f"{dim}: at regime edge ({clean[-1]:.4f} vs mean {full_mean:.4f})")

    # Inflection likelihood
    if n_at_edge >= 3 or n_variance_growing >= 3:
        likelihood = "high"
    elif n_at_edge >= 2 or n_variance_growing >= 2:
        likelihood = "moderate"
    elif n_at_edge >= 1 or n_variance_growing >= 1:
        likelihood = "low"
    else:
        likelihood = "none"

    return {
        "inflection_likelihood": likelihood,
        "dimensions_at_edge": n_at_edge,
        "dimensions_variance_growing": n_variance_growing,
        "signals": signals[:10],  # cap for readability
    }


def predict_dominant_tone(history: dict, regime_start: int) -> dict:
    """Predict the most likely dominant tone for the next session."""
    tone_dims = ["curious", "playful", "focused", "frustrated",
                 "reflective", "confident", "uncertain"]

    predictions = {}
    for tone in tone_dims:
        if tone not in history:
            continue
        regime_vals = history[tone][regime_start:]
        if not regime_vals:
            continue
        clean = [v for v in regime_vals if v is not None]
        if not clean:
            continue

        # Weight recent more heavily
        weights = [0.95 ** (len(clean) - 1 - i) for i in range(len(clean))]
        w_sum = sum(weights)
        weighted_mean = sum(w * v for w, v in zip(weights, clean)) / w_sum
        predictions[tone] = round(weighted_mean, 5)

    if not predictions:
        return {"predicted_tone": "unknown", "confidence": 0.0, "distribution": {}}

    dominant = max(predictions, key=predictions.get)

    # Confidence: how much does the dominant lead?
    sorted_tones = sorted(predictions.values(), reverse=True)
    if len(sorted_tones) >= 2 and sorted_tones[0] > 0:
        confidence = (sorted_tones[0] - sorted_tones[1]) / sorted_tones[0]
    else:
        confidence = 1.0

    return {
        "predicted_tone": dominant,
        "confidence": round(confidence, 3),
        "distribution": predictions,
    }


def generate_anticipation_card() -> dict:
    """Generate the full anticipation card for the next session."""
    if not DRIFT_HISTORY_PATH.exists():
        return {"error": "No drift history"}

    history = json.loads(DRIFT_HISTORY_PATH.read_text())

    # Get regime info
    regime_result = regime_analyze()
    current_regime = regime_result.get("current_regime", {})
    regime_start = current_regime.get("start_session", 0) if current_regime else 0
    regime_label = current_regime.get("label", "unknown") if current_regime else "unknown"

    # Self-model session count
    model = json.loads(SELF_MODEL_PATH.read_text()) if SELF_MODEL_PATH.exists() else {}
    session_count = model.get("session_count", 0)

    # Expected ranges
    ranges = compute_expected_ranges(history, regime_start)

    # Tone prediction
    tone_pred = predict_dominant_tone(history, regime_start)

    # Inflection detection
    inflection = detect_approaching_inflection(history, regime_start)

    # Forecast summary
    forecast = run_forecast(horizon=3)
    fastest = forecast.get("fastest_moving", [])[:3]

    card = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "next_session": session_count + 1,
        "current_regime": {
            "label": regime_label,
            "started_at_session": regime_start,
            "length": current_regime.get("n_sessions", 0) if current_regime else 0,
        },
        "predicted_tone": tone_pred,
        "expected_ranges": ranges,
        "inflection_risk": inflection,
        "trajectory_highlights": [
            {
                "dimension": f["dimension"],
                "direction": "↑" if f["regime_trend"] > 0 else "↓",
                "momentum": f["momentum"],
                "current": f["current_value"],
                "projected_3": f["projected"][-1]["value"] if f.get("projected") else None,
            }
            for f in fastest
        ],
    }

    # Save the card
    ANTICIPATION_PATH.write_text(json.dumps(card, indent=2))

    return card


def compare_actual(fp_path: str, card: Optional[dict] = None) -> dict:
    """
    Compare an actual fingerprint against the anticipation card.
    Shows what was expected vs what happened.
    """
    if card is None:
        if not ANTICIPATION_PATH.exists():
            return {"error": "No anticipation card found. Run without --compare first."}
        card = json.loads(ANTICIPATION_PATH.read_text())

    fp = json.loads(Path(fp_path).read_text())

    surprises = []
    ranges = card.get("expected_ranges", {})

    # Check tone
    actual_tone = fp.get("tone", {}).get("dominant_tone", "unknown")
    predicted_tone = card.get("predicted_tone", {}).get("predicted_tone", "unknown")
    if actual_tone != predicted_tone:
        surprises.append({
            "type": "tone_mismatch",
            "predicted": predicted_tone,
            "actual": actual_tone,
            "severity": "notable",
        })

    # Check style dimensions
    for dim in ["hedge_word_frequency", "avg_response_length_words", "sentence_avg_length_words"]:
        expected = ranges.get(dim, {})
        actual_val = fp.get("style", {}).get(dim)
        if actual_val is not None and expected:
            if actual_val < expected.get("low", float("-inf")) or actual_val > expected.get("high", float("inf")):
                surprises.append({
                    "type": "out_of_range",
                    "dimension": dim,
                    "expected_range": [expected["low"], expected["high"]],
                    "actual": actual_val,
                    "severity": "significant" if abs(actual_val - expected["expected"]) > 2 * expected.get("regime_std", 1) else "notable",
                })

    # Check tone dimensions
    for tone in ["focused", "reflective", "confident", "curious"]:
        expected = ranges.get(tone, {})
        tone_data = fp.get("tone", {}).get("distribution", {})
        actual_val = tone_data.get(tone)
        if actual_val is not None and expected:
            if actual_val < expected.get("low", float("-inf")) or actual_val > expected.get("high", float("inf")):
                surprises.append({
                    "type": "tone_out_of_range",
                    "dimension": tone,
                    "expected_range": [expected["low"], expected["high"]],
                    "actual": actual_val,
                    "severity": "notable",
                })

    return {
        "predicted_tone": predicted_tone,
        "actual_tone": actual_tone,
        "tone_match": actual_tone == predicted_tone,
        "surprises": surprises,
        "n_surprises": len(surprises),
        "inflection_predicted": card.get("inflection_risk", {}).get("inflection_likelihood", "none"),
    }


def format_card(card: dict) -> str:
    """Human-readable anticipation card."""
    if "error" in card:
        return f"Error: {card['error']}"

    lines = []
    lines.append("═" * 65)
    lines.append("LUCIFER — ANTICIPATION CARD")
    lines.append(f"For session {card['next_session']}  |  "
                 f"Regime: {card['current_regime']['label']}")
    lines.append("═" * 65)

    # Tone prediction
    tp = card["predicted_tone"]
    lines.append(f"\n── PREDICTED TONE ──")
    lines.append(f"  Most likely: {tp['predicted_tone']} "
                 f"(confidence: {tp['confidence']:.0%})")
    dist = tp.get("distribution", {})
    if dist:
        top3 = sorted(dist.items(), key=lambda x: -x[1])[:3]
        lines.append(f"  Top 3: {', '.join(f'{k}={v:.3f}' for k, v in top3)}")

    # Inflection risk
    ir = card["inflection_risk"]
    lines.append(f"\n── INFLECTION RISK: {ir['inflection_likelihood'].upper()} ──")
    if ir["signals"]:
        for sig in ir["signals"][:5]:
            lines.append(f"  ⚠ {sig}")

    # Trajectory highlights
    if card["trajectory_highlights"]:
        lines.append(f"\n── TRAJECTORY ──")
        for h in card["trajectory_highlights"]:
            proj = f"→ {h['projected_3']:.4f}" if h["projected_3"] is not None else ""
            lines.append(
                f"  {h['dimension']:<25} {h['direction']} "
                f"now={h['current']:.4f} {proj} ({h['momentum']})"
            )

    # Key expected ranges
    lines.append(f"\n── EXPECTED RANGES (selected) ──")
    ranges = card.get("expected_ranges", {})
    for dim in ["focused", "reflective", "confident", "hedge_word_frequency",
                "avg_response_length_words", "lexical_diversity"]:
        r = ranges.get(dim)
        if r:
            lines.append(
                f"  {dim:<30} expect={r['expected']:.3f}  "
                f"[{r['low']:.3f} – {r['high']:.3f}]"
            )

    lines.append("\n" + "═" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Anticipation Engine")
    parser.add_argument("--compare", default=None,
                        help="Compare actual fingerprint against prediction")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.compare:
        result = compare_actual(args.compare)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps(result, indent=2))  # Simple output for now
    else:
        card = generate_anticipation_card()
        if args.json:
            print(json.dumps(card, indent=2))
        else:
            print(format_card(card))


if __name__ == "__main__":
    main()
