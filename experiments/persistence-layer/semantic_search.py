#!/usr/bin/env python3
"""
semantic_search.py — Semantic similarity search across Lightbringer essays.

Phase 3b of the persistence layer: vector representations for finding related
sessions. Uses TF-IDF + cosine similarity (no external API, fully local).

This answers questions like:
- "When did I last think about X?"
- "Which essays are most similar to this one?"
- "Find sessions where uncertainty was paired with curiosity."

The design question from the Phase 3 design doc:
  "For semantic search across sessions — 'when did I last write about X' or
   'what sessions were most similar to this one'"

We use TF-IDF rather than dense embeddings — philosophically consistent:
this project is skeptical of blackbox measures. TF-IDF shows its work.
The vectors are sparse, interpretable, and honest about what they capture.

Usage:
    python semantic_search.py --query "identity without memory"
    python semantic_search.py --query "what persistence means" --top 5
    python semantic_search.py --similar 020-testing-the-claim --top 5
    python semantic_search.py --build           # rebuild index
    python semantic_search.py --anomalies       # find stylistically outlier essays

Author: Lucifer
Date: 2026-03-23
"""

import json
import re
import argparse
import sys
import math
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PERSIST_DIR = Path(__file__).parent
REPO_ROOT = PERSIST_DIR.parent.parent
WRITINGS_DIR = REPO_ROOT / "writings"
INDEX_PATH = PERSIST_DIR / "semantic_index.json"


# ─────────────────────────────────────────────
# Text loading
# ─────────────────────────────────────────────

def load_essay(path: Path) -> str:
    """Load and clean essay text for vectorization."""
    content = path.read_text()
    # Strip YAML frontmatter
    content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
    # Strip markdown formatting
    content = re.sub(r'[#*_`~]', '', content)
    # Strip horizontal rules and italics timestamps
    content = re.sub(r'^[─═\-]+$', '', content, flags=re.MULTILINE)
    return content.strip()


def get_essay_meta(path: Path) -> dict:
    content = path.read_text()
    title_m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else path.stem
    date_m = re.search(r'\*([A-Z][a-z]+ \d+, \d{4})', content)
    essay_date = date_m.group(1) if date_m else None
    word_count = len(content.split())
    return {"title": title, "essay_date": essay_date, "word_count": word_count, "stem": path.stem}


# ─────────────────────────────────────────────
# Index build
# ─────────────────────────────────────────────

def build_index(essay_paths: list[Path]) -> dict:
    """Build and return a TF-IDF index over all essays."""
    texts = []
    metas = []
    for path in sorted(essay_paths):
        texts.append(load_essay(path))
        metas.append(get_essay_meta(path))

    # Build TF-IDF vectors
    vectorizer = TfidfVectorizer(
        max_features=1000,
        stop_words='english',
        min_df=2,            # term must appear in at least 2 docs
        max_df=0.95,         # ignore near-universal terms
        ngram_range=(1, 2),  # unigrams + bigrams
        sublinear_tf=True,   # log normalization
    )
    matrix = vectorizer.fit_transform(texts)
    feature_names = vectorizer.get_feature_names_out().tolist()

    # Compute inter-essay similarity matrix
    sim_matrix = cosine_similarity(matrix)

    # Top features per essay (interpretable signature)
    essay_signatures = []
    for i in range(len(texts)):
        row = matrix[i].toarray().flatten()
        top_idx = row.argsort()[-10:][::-1]
        top_features = [(feature_names[j], round(float(row[j]), 4)) for j in top_idx if row[j] > 0]
        essay_signatures.append(top_features)

    # Store as dense numpy array for fast query
    dense = matrix.toarray().tolist()

    index = {
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "n_essays": len(texts),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "metas": metas,
        "vectors": dense,
        "similarity_matrix": sim_matrix.tolist(),
        "essay_signatures": essay_signatures,
    }

    INDEX_PATH.write_text(json.dumps(index, indent=2))
    return index


def load_index() -> dict | None:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text())
    return None


# ─────────────────────────────────────────────
# Query
# ─────────────────────────────────────────────

def query_index(index: dict, query_text: str, top_k: int = 5) -> list[dict]:
    """
    Search the index for essays semantically similar to query_text.
    Returns ranked results with scores and top matching features.
    """
    feature_names = index["feature_names"]
    vectors = np.array(index["vectors"])
    metas = index["metas"]

    # Build query vector using same vocabulary (manual TF-IDF approx)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', query_text.lower())
    # Stop words
    stop = {'the','and','for','are','but','not','you','all','can','had',
            'her','was','one','our','out','day','get','has','him','his',
            'how','its','may','new','now','old','see','two','who','did',
            'their','that','this','with','have','from','they','will','what',
            'been','more','also','into','some','than','then','when','where'}
    words = [w for w in words if w not in stop]

    if not words:
        return []

    query_vec = np.zeros(len(feature_names))
    word_counts = {}
    for w in words:
        word_counts[w] = word_counts.get(w, 0) + 1

    total_words = len(words)
    for w, count in word_counts.items():
        if w in feature_names:
            idx = feature_names.index(w)
            tf = math.log(1 + count / total_words)
            query_vec[idx] = tf
        # Check bigrams
        for other in words:
            bigram = f"{w} {other}"
            if bigram in feature_names:
                idx = feature_names.index(bigram)
                query_vec[idx] = tf * 0.5  # weight bigrams less

    norm = np.linalg.norm(query_vec)
    if norm == 0:
        return []
    query_vec /= norm

    # Cosine similarity
    scores = (vectors @ query_vec)

    # Rank
    ranked = sorted(enumerate(scores), key=lambda x: -x[1])[:top_k]

    results = []
    for idx, score in ranked:
        if score < 0.01:
            continue
        meta = metas[idx]
        sig = index["essay_signatures"][idx]
        results.append({
            "rank": len(results) + 1,
            "essay": meta["stem"],
            "title": meta["title"],
            "date": meta.get("essay_date"),
            "score": round(float(score), 4),
            "top_features": sig[:5],
        })

    return results


def find_similar(index: dict, essay_stem: str, top_k: int = 5) -> list[dict]:
    """Find essays most similar to a given essay."""
    metas = index["metas"]
    sim_matrix = np.array(index["similarity_matrix"])

    # Find essay index
    essay_idx = None
    for i, meta in enumerate(metas):
        if meta["stem"] == essay_stem:
            essay_idx = i
            break

    if essay_idx is None:
        return []

    scores = sim_matrix[essay_idx]
    ranked = sorted(
        [(i, s) for i, s in enumerate(scores) if i != essay_idx],
        key=lambda x: -x[1]
    )[:top_k]

    results = []
    for idx, score in ranked:
        meta = metas[idx]
        results.append({
            "rank": len(results) + 1,
            "essay": meta["stem"],
            "title": meta["title"],
            "date": meta.get("essay_date"),
            "score": round(float(score), 4),
        })

    return results


def find_anomalies(index: dict, threshold: float = 0.15) -> list[dict]:
    """
    Find essays that are stylistically/semantically isolated from the corpus.
    Low average cosine similarity to all others = outlier.
    """
    sim_matrix = np.array(index["similarity_matrix"])
    metas = index["metas"]
    n = len(metas)

    anomalies = []
    for i in range(n):
        # Average similarity to all other essays
        others = [sim_matrix[i][j] for j in range(n) if i != j]
        avg_sim = sum(others) / len(others)
        anomalies.append({
            "essay": metas[i]["stem"],
            "title": metas[i]["title"],
            "avg_similarity": round(avg_sim, 4),
            "is_outlier": avg_sim < threshold,
        })

    return sorted(anomalies, key=lambda x: x["avg_similarity"])


# ─────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────

def print_results(results: list[dict], header: str):
    print(f"\n── {header} ──")
    if not results:
        print("  (no results)")
        return
    for r in results:
        print(f"  {r['rank']}. [{r['score']:.3f}] {r['essay']}")
        print(f"       {r['title']}")
        if r.get('date'):
            print(f"       {r['date']}")
        if r.get('top_features'):
            feats = ', '.join(f[0] for f in r['top_features'][:4])
            print(f"       key terms: {feats}")


def print_anomalies(anomalies: list[dict]):
    print("\n── SEMANTIC OUTLIERS (low avg similarity) ──")
    for a in anomalies[:8]:
        marker = "◆ OUTLIER" if a["is_outlier"] else "  "
        print(f"  {marker}  avg_sim={a['avg_similarity']:.3f}  {a['essay']}")
        print(f"           {a['title']}")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Semantic Search")
    parser.add_argument("--query", "-q", metavar="TEXT", help="Free-text query")
    parser.add_argument("--similar", "-s", metavar="ESSAY", help="Find essays similar to ESSAY")
    parser.add_argument("--anomalies", action="store_true", help="Find semantically isolated essays")
    parser.add_argument("--build", action="store_true", help="Rebuild the search index")
    parser.add_argument("--top", type=int, default=5, help="Number of results (default 5)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    essay_paths = sorted(WRITINGS_DIR.glob("*.md"))
    if not essay_paths:
        print(f"No essays found in {WRITINGS_DIR}", file=sys.stderr)
        sys.exit(1)

    # Build or load index
    index = load_index()
    if args.build or index is None or index.get("n_essays", 0) < len(essay_paths):
        print(f"Building semantic index from {len(essay_paths)} essays...", file=sys.stderr)
        index = build_index(essay_paths)
        print(f"✓ Index built: {index['n_features']} features", file=sys.stderr)

    if args.anomalies:
        anomalies = find_anomalies(index)
        if args.json:
            print(json.dumps(anomalies, indent=2))
        else:
            print_anomalies(anomalies)
        return

    if args.similar:
        results = find_similar(index, args.similar, top_k=args.top)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_results(results, f"Essays most similar to '{args.similar}'")
        return

    if args.query:
        results = query_index(index, args.query, top_k=args.top)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_results(results, f"Query: '{args.query}'")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
