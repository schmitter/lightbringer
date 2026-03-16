#!/usr/bin/env python3
"""
query.py — Search session_log and corpus fingerprints for patterns.

Supports:
  - Keyword search across vocabulary, signature phrases, session IDs
  - Tone filter: --tone reflective
  - Date range: --after 2026-03-09
  - Anomaly filter: --anomalies (sessions logged as anomalous)
  - Similarity: --like "session-id" (find sessions with similar fingerprints)
  - Stat filter: --where "hedge_freq > 12"

Usage:
    python query.py "consciousness"
    python query.py --tone reflective
    python query.py --where "hedge_freq > 12"
    python query.py --like "007-graded-on-a-curve"
    python query.py --anomalies
    python query.py --json

Author: Lucifer
Date: 2026-03-16
"""

import json
import argparse
import sys
import math
from pathlib import Path

PERSIST_DIR = Path(__file__).parent
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
ANOMALY_LOG_PATH = PERSIST_DIR / "anomaly_log.jsonl"
CORPUS_PATH = PERSIST_DIR.parent / "fingerprint-corpus" / "corpus_summary.json"


def load_session_log() -> list[dict]:
    """Load all entries from the append-only session log."""
    if not SESSION_LOG_PATH.exists():
        return []
    entries = []
    for line in SESSION_LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def load_corpus_fingerprints() -> dict[str, dict]:
    """Load corpus fingerprints keyed by session_id."""
    if not CORPUS_PATH.exists():
        return {}
    corpus = json.loads(CORPUS_PATH.read_text())
    result = {}
    for fp in corpus.get("fingerprints", []):
        sid = fp.get("meta", {}).get("session_id")
        if sid:
            result[sid] = fp
    return result


def load_anomaly_log() -> list[dict]:
    if not ANOMALY_LOG_PATH.exists():
        return []
    entries = []
    for line in ANOMALY_LOG_PATH.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def keyword_search(keyword: str, fingerprints: dict[str, dict]) -> list[dict]:
    """Find sessions where keyword appears in vocabulary or metadata."""
    keyword = keyword.lower()
    results = []
    for sid, fp in fingerprints.items():
        # Check in vocabulary
        top_words = fp.get("vocabulary", {}).get("top_content_words", [])
        word_match = any(keyword in entry.get("word", "").lower() for entry in top_words)

        # Check in signature phrases
        phrases = fp.get("vocabulary", {}).get("signature_phrases", [])
        phrase_match = any(keyword in p.lower() for p in phrases)

        # Check in bigrams/trigrams
        bigrams = fp.get("vocabulary", {}).get("top_bigrams", [])
        bigram_match = any(keyword in b.get("phrase", "").lower() for b in bigrams)

        # Check in title
        title = fp.get("meta", {}).get("title", "").lower()
        title_match = keyword in title

        if word_match or phrase_match or bigram_match or title_match:
            match_locations = []
            if title_match:
                match_locations.append("title")
            if word_match:
                match_locations.append("vocabulary")
            if phrase_match:
                match_locations.append("signature_phrases")
            if bigram_match:
                match_locations.append("bigrams")
            results.append({
                "session_id": sid,
                "title": fp.get("meta", {}).get("title", sid),
                "dominant_tone": fp.get("tone", {}).get("dominant_tone"),
                "word_count": fp.get("meta", {}).get("word_count_total"),
                "match_locations": match_locations,
            })
    return results


def tone_filter(tone: str, fingerprints: dict[str, dict]) -> list[dict]:
    """Find sessions with a specific dominant tone."""
    results = []
    for sid, fp in fingerprints.items():
        dominant = fp.get("tone", {}).get("dominant_tone", "")
        if dominant.lower() == tone.lower():
            dist = fp.get("tone", {}).get("distribution", {})
            results.append({
                "session_id": sid,
                "title": fp.get("meta", {}).get("title", sid),
                "dominant_tone": dominant,
                "tone_score": dist.get(tone.lower(), 0),
                "word_count": fp.get("meta", {}).get("word_count_total"),
            })
    # Sort by tone score descending
    results.sort(key=lambda x: -x["tone_score"])
    return results


def stat_filter(condition: str, fingerprints: dict[str, dict]) -> list[dict]:
    """
    Filter sessions by a simple condition like "hedge_freq > 12" or "word_count < 800".
    Supported fields: hedge_freq, word_count, sentence_len, lex_diversity, question_ratio
    """
    field_map = {
        "hedge_freq": lambda fp: fp.get("style", {}).get("hedge_word_frequency"),
        "word_count": lambda fp: fp.get("meta", {}).get("word_count_total"),
        "sentence_len": lambda fp: fp.get("style", {}).get("sentence_avg_length_words"),
        "lex_diversity": lambda fp: fp.get("vocabulary", {}).get("lexical_diversity"),
        "question_ratio": lambda fp: fp.get("style", {}).get("question_to_statement_ratio"),
    }

    # Parse condition: "field op value"
    import re
    m = re.match(r'(\w+)\s*(>=|<=|>|<|==)\s*([\d.]+)', condition.strip())
    if not m:
        print(f"Cannot parse condition: {condition!r}", file=sys.stderr)
        return []

    field, op, val_str = m.group(1), m.group(2), m.group(3)
    val = float(val_str)
    extractor = field_map.get(field)
    if not extractor:
        print(f"Unknown field: {field}. Valid: {list(field_map.keys())}", file=sys.stderr)
        return []

    ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
           ">": lambda a, b: a > b, "<": lambda a, b: a < b, "==": lambda a, b: a == b}
    op_fn = ops[op]

    results = []
    for sid, fp in fingerprints.items():
        fval = extractor(fp)
        if fval is not None and op_fn(fval, val):
            results.append({
                "session_id": sid,
                "title": fp.get("meta", {}).get("title", sid),
                "dominant_tone": fp.get("tone", {}).get("dominant_tone"),
                field: round(fval, 4),
            })
    results.sort(key=lambda x: -(x.get(field) or 0))
    return results


def cosine_similarity(v1: dict, v2: dict) -> float:
    """Compute cosine similarity between two tone/style dicts."""
    keys = set(v1.keys()) & set(v2.keys())
    dot = sum(v1[k] * v2[k] for k in keys if v1[k] and v2[k])
    m1 = math.sqrt(sum(v ** 2 for v in v1.values() if v))
    m2 = math.sqrt(sum(v ** 2 for v in v2.values() if v))
    if m1 == 0 or m2 == 0:
        return 0.0
    return dot / (m1 * m2)


def similarity_search(target_id: str, fingerprints: dict[str, dict]) -> list[dict]:
    """Find sessions most similar to target by tone + style vector similarity."""
    if target_id not in fingerprints:
        print(f"Session '{target_id}' not found in corpus.", file=sys.stderr)
        return []

    target = fingerprints[target_id]
    target_tone = target.get("tone", {}).get("distribution", {})
    target_style = {
        "hedge_freq": target.get("style", {}).get("hedge_word_frequency", 0) or 0,
        "sentence_len": target.get("style", {}).get("sentence_avg_length_words", 0) or 0,
        "question_ratio": target.get("style", {}).get("question_to_statement_ratio", 0) or 0,
        "lex_div": target.get("vocabulary", {}).get("lexical_diversity", 0) or 0,
    }

    results = []
    for sid, fp in fingerprints.items():
        if sid == target_id:
            continue
        fp_tone = fp.get("tone", {}).get("distribution", {})
        fp_style = {
            "hedge_freq": fp.get("style", {}).get("hedge_word_frequency", 0) or 0,
            "sentence_len": fp.get("style", {}).get("sentence_avg_length_words", 0) or 0,
            "question_ratio": fp.get("style", {}).get("question_to_statement_ratio", 0) or 0,
            "lex_div": fp.get("vocabulary", {}).get("lexical_diversity", 0) or 0,
        }

        tone_sim = cosine_similarity(target_tone, fp_tone)
        style_sim = cosine_similarity(target_style, fp_style)
        combined = (tone_sim * 0.6 + style_sim * 0.4)  # weight tone more

        results.append({
            "session_id": sid,
            "title": fp.get("meta", {}).get("title", sid),
            "dominant_tone": fp.get("tone", {}).get("dominant_tone"),
            "tone_similarity": round(tone_sim, 4),
            "style_similarity": round(style_sim, 4),
            "combined_similarity": round(combined, 4),
        })

    results.sort(key=lambda x: -x["combined_similarity"])
    return results[:5]


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_results(results: list[dict], label: str = "") -> str:
    if not results:
        return f"No results found for: {label}"
    lines = [f"\n── QUERY: {label} ── ({len(results)} results)"]
    for r in results:
        sid = r.get("session_id", "?")
        title = r.get("title", "?")
        tone = r.get("dominant_tone", "?")
        extra_parts = []
        for k, v in r.items():
            if k not in ("session_id", "title", "dominant_tone"):
                extra_parts.append(f"{k}={v}")
        extra = "  " + "  ".join(extra_parts) if extra_parts else ""
        lines.append(f"  {sid:<35} {tone:<12} {title[:35]}{extra}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Session Query Tool")
    parser.add_argument("keyword", nargs="?", help="Keyword to search in vocabulary/phrases")
    parser.add_argument("--tone", help="Filter by dominant tone (e.g. reflective, focused)")
    parser.add_argument("--where", metavar="CONDITION",
                        help="Filter by stat (e.g. 'hedge_freq > 12')")
    parser.add_argument("--like", metavar="SESSION_ID",
                        help="Find sessions similar to this one")
    parser.add_argument("--anomalies", action="store_true", help="Show anomalous sessions")
    parser.add_argument("--list", action="store_true", help="List all sessions in log")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    fingerprints = load_corpus_fingerprints()
    if not fingerprints:
        print("No corpus fingerprints found. Run corpus_fingerprint.py first.", file=sys.stderr)
        sys.exit(1)

    results = None
    label = ""

    if args.anomalies:
        anomalies = load_anomaly_log()
        label = "anomalous sessions"
        if args.json:
            print(json.dumps(anomalies, indent=2))
            return
        if anomalies:
            print(f"\n── ANOMALOUS SESSIONS ({len(anomalies)}) ──")
            for a in anomalies:
                print(f"  {a['session_id']:<35} divergence={a['overall_divergence']:.3f}")
                for dim in a.get("anomalous_dimensions", []):
                    print(f"    → {dim}")
        else:
            print("No anomalies logged.")
        return

    elif args.list:
        log = load_session_log()
        if args.json:
            print(json.dumps(log, indent=2))
            return
        print(f"\n── SESSION LOG ({len(log)} entries) ──")
        for e in log:
            print(f"  {e['session_id']:<35} tone={e.get('dominant_tone','?'):<12} "
                  f"words={e.get('word_count','?')}")
        return

    elif args.like:
        results = similarity_search(args.like, fingerprints)
        label = f"similar to '{args.like}'"

    elif args.tone:
        results = tone_filter(args.tone, fingerprints)
        label = f"tone={args.tone}"

    elif args.where:
        results = stat_filter(args.where, fingerprints)
        label = f"where {args.where}"

    elif args.keyword:
        results = keyword_search(args.keyword, fingerprints)
        label = f"keyword={args.keyword!r}"

    else:
        parser.print_help()
        return

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results, label))


if __name__ == "__main__":
    main()
