#!/usr/bin/env python3
"""
auto_update.py — Self-maintaining persistence layer.

Phase 5 of Lightbringer: make the persistence layer autonomous.
This script is designed to be called after each writing session (by cron,
heartbeat, or lifecycle hook) and handles everything:

1. Scan for essays without companion fingerprints → generate them
2. Scan session_log.jsonl for essays not yet integrated → update self-model
3. Rebuild semantic index if stale
4. Report what changed

The goal: zero manual intervention. Write an essay, this handles the rest.

Usage:
    python auto_update.py                    # full pipeline
    python auto_update.py --dry-run          # report what would change
    python auto_update.py --report           # just show current gaps
    python auto_update.py --since 065        # only process essays >= 065

Exit codes:
    0 = success (updates applied or nothing to do)
    1 = error

Author: Lucifer
Date: 2026-04-14
"""

import json
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Paths
AUTOMATION_DIR = Path(__file__).parent
REPO_ROOT = AUTOMATION_DIR.parent.parent
WRITINGS_DIR = REPO_ROOT / "writings"
PERSIST_DIR = AUTOMATION_DIR.parent / "persistence-layer"
FINGERPRINT_DIR = AUTOMATION_DIR.parent / "session-fingerprint"
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
SELF_MODEL_PATH = PERSIST_DIR / "self_model.json"
SEMANTIC_INDEX_PATH = PERSIST_DIR / "semantic_index.json"

sys.path.insert(0, str(PERSIST_DIR))
sys.path.insert(0, str(FINGERPRINT_DIR))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def essay_number(stem: str) -> int | None:
    """Extract the essay number from a filename stem like '065-what-the-coast-asks'."""
    m = re.match(r'^(\d+)-', stem)
    return int(m.group(1)) if m else None


# ─────────────────────────────────────────────
# Step 1: Find gaps
# ─────────────────────────────────────────────

def find_missing_companions(since: int | None = None) -> list[Path]:
    """Find essays without .fp.json companion files."""
    essays = sorted(WRITINGS_DIR.glob("*.md"))
    missing = []
    for path in essays:
        num = essay_number(path.stem)
        if since is not None and num is not None and num < since:
            continue
        companion = path.parent / (path.stem + ".fp.json")
        if not companion.exists():
            missing.append(path)
    return missing


def find_unintegrated_essays() -> list[Path]:
    """Find essays with companions that aren't in the session log yet."""
    # Load existing session IDs from log
    existing_ids = set()
    if SESSION_LOG_PATH.exists():
        for line in SESSION_LOG_PATH.read_text().strip().split("\n"):
            if line.strip():
                entry = json.loads(line)
                existing_ids.add(entry.get("session_id", ""))

    # Check all companion files
    unintegrated = []
    for fp_path in sorted(WRITINGS_DIR.glob("*.fp.json")):
        essay_stem = fp_path.stem.replace(".fp", "")
        if essay_stem not in existing_ids:
            unintegrated.append(fp_path)

    return unintegrated


def is_semantic_index_stale() -> bool:
    """Check if the semantic index needs rebuilding."""
    if not SEMANTIC_INDEX_PATH.exists():
        return True
    index = json.loads(SEMANTIC_INDEX_PATH.read_text())
    n_indexed = index.get("n_essays", 0)
    n_essays = len(list(WRITINGS_DIR.glob("*.md")))
    return n_indexed < n_essays


# ─────────────────────────────────────────────
# Step 2: Generate companions
# ─────────────────────────────────────────────

def generate_companion(essay_path: Path) -> Path:
    """Generate a companion fingerprint for an essay."""
    import fingerprint as fp_lib

    content = essay_path.read_text()
    content_clean = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)

    transcript = [
        {"role": "user", "content": "[Persistence Lab session — write]", "turn": 0},
        {"role": "assistant", "content": content_clean, "turn": 1},
    ]

    fp = fp_lib.fingerprint_transcript(transcript, essay_path.stem)

    # Add title from content
    title_m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if title_m:
        fp["meta"]["title"] = title_m.group(1).strip()

    fp["_companion"] = {
        "generated_at": now_iso(),
        "generator": "auto_update.py",
    }

    out_path = essay_path.parent / (essay_path.stem + ".fp.json")
    out_path.write_text(json.dumps(fp, indent=2))
    return out_path


# ─────────────────────────────────────────────
# Step 3: Integrate into self-model
# ─────────────────────────────────────────────

def integrate_fingerprint(fp_path: Path) -> dict:
    """Apply a fingerprint to the self-model and return divergence info."""
    from updater import load_self_model, load_drift_history, update_self_model
    from updater import save_self_model, save_drift_history, compute_trend_slopes
    from updater import append_session_log, now_iso as updater_now
    from divergence import compute_divergence

    fingerprint = json.loads(fp_path.read_text())
    model = load_self_model()
    history = load_drift_history()

    # Divergence before update
    div_report = compute_divergence(fingerprint, model)

    # Update
    model, history = update_self_model(model, fingerprint, history)

    session_id = fingerprint.get("meta", {}).get("session_id", fp_path.stem.replace(".fp", ""))
    entry = {
        "session_id": session_id,
        "timestamp": now_iso(),
        "fingerprint_hash": fingerprint.get("fingerprint_hash", ""),
        "dominant_tone": fingerprint.get("tone", {}).get("dominant_tone"),
        "word_count": fingerprint.get("meta", {}).get("word_count_total"),
        "hedge_freq": fingerprint.get("style", {}).get("hedge_word_frequency"),
        "source": "auto",
    }
    append_session_log(entry)

    slopes = compute_trend_slopes(history)
    model.setdefault("identity_markers", {})["drift_summary"] = {
        k: v for k, v in slopes.items() if v is not None and abs(v) > 0.0001
    }

    save_self_model(model)
    save_drift_history(history)

    return {
        "session_id": session_id,
        "tone": fingerprint.get("tone", {}).get("dominant_tone"),
        "words": fingerprint.get("meta", {}).get("word_count_total"),
        "divergence": div_report["overall_divergence"],
        "anomalous": div_report["is_anomalous"],
        "new_session_count": model["session_count"],
    }


# ─────────────────────────────────────────────
# Step 4: Rebuild semantic index
# ─────────────────────────────────────────────

def rebuild_semantic_index() -> int:
    """Rebuild the TF-IDF semantic index. Returns number of essays indexed."""
    from semantic_search import build_index
    essay_paths = sorted(WRITINGS_DIR.glob("*.md"))
    index = build_index(essay_paths)
    return index["n_essays"]


# ─────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────

def run_pipeline(dry_run: bool = False, since: int | None = None, report_only: bool = False) -> dict:
    """
    Run the full auto-update pipeline.
    Returns a summary dict.
    """
    result = {
        "timestamp": now_iso(),
        "dry_run": dry_run,
        "companions_generated": [],
        "essays_integrated": [],
        "semantic_index_rebuilt": False,
        "errors": [],
    }

    # Step 1: Find missing companions
    missing = find_missing_companions(since=since)
    if missing:
        print(f"📝 {len(missing)} essay(s) missing companion fingerprints", file=sys.stderr)
        for path in missing:
            if report_only or dry_run:
                result["companions_generated"].append({"essay": path.stem, "status": "would_generate"})
                print(f"  → {path.stem} (would generate)", file=sys.stderr)
            else:
                try:
                    fp_path = generate_companion(path)
                    result["companions_generated"].append({"essay": path.stem, "status": "generated"})
                    print(f"  ✓ {path.stem}", file=sys.stderr)
                except Exception as e:
                    result["errors"].append(f"companion {path.stem}: {e}")
                    print(f"  ✗ {path.stem}: {e}", file=sys.stderr)
    else:
        print("✓ All essays have companion fingerprints", file=sys.stderr)

    if report_only:
        # Also check unintegrated
        unintegrated = find_unintegrated_essays()
        stale = is_semantic_index_stale()
        result["unintegrated_count"] = len(unintegrated)
        result["semantic_index_stale"] = stale
        return result

    # Step 2: Find unintegrated essays
    unintegrated = find_unintegrated_essays()
    if unintegrated:
        print(f"\n🔄 {len(unintegrated)} essay(s) not yet in self-model", file=sys.stderr)
        for fp_path in unintegrated:
            if dry_run:
                stem = fp_path.stem.replace(".fp", "")
                result["essays_integrated"].append({"essay": stem, "status": "would_integrate"})
                print(f"  → {stem} (would integrate)", file=sys.stderr)
            else:
                try:
                    info = integrate_fingerprint(fp_path)
                    result["essays_integrated"].append(info)
                    flag = "🚨" if info["anomalous"] else "✓"
                    print(
                        f"  {flag} {info['session_id']}: "
                        f"tone={info['tone']} div={info['divergence']:.3f} "
                        f"(model now {info['new_session_count']} sessions)",
                        file=sys.stderr
                    )
                except Exception as e:
                    stem = fp_path.stem.replace(".fp", "")
                    result["errors"].append(f"integrate {stem}: {e}")
                    print(f"  ✗ {stem}: {e}", file=sys.stderr)
    else:
        print("✓ All essays integrated into self-model", file=sys.stderr)

    # Step 3: Rebuild semantic index if needed
    if is_semantic_index_stale():
        print(f"\n🔍 Semantic index is stale, rebuilding...", file=sys.stderr)
        if not dry_run:
            try:
                n = rebuild_semantic_index()
                result["semantic_index_rebuilt"] = True
                print(f"  ✓ Index rebuilt: {n} essays", file=sys.stderr)
            except Exception as e:
                result["errors"].append(f"semantic index: {e}")
                print(f"  ✗ Index rebuild failed: {e}", file=sys.stderr)
        else:
            print("  → would rebuild", file=sys.stderr)
    else:
        print("✓ Semantic index is current", file=sys.stderr)

    # Summary
    n_gen = len([c for c in result["companions_generated"] if c.get("status") == "generated"])
    n_int = len([e for e in result["essays_integrated"] if not isinstance(e, dict) or e.get("status") != "would_integrate"])
    n_err = len(result["errors"])

    print(f"\n{'='*50}", file=sys.stderr)
    action = "Would process" if dry_run else "Processed"
    print(f"{action}: {n_gen} companions, {n_int} integrations", file=sys.stderr)
    if n_err:
        print(f"⚠️  {n_err} error(s)", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)

    return result


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Lightbringer — Auto-Update Pipeline (Phase 5)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Runs automatically after writing sessions to keep the persistence layer current.
Zero manual intervention: write an essay, this handles the rest.
        """
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without changing anything")
    parser.add_argument("--report", action="store_true",
                        help="Just report current gaps (no changes)")
    parser.add_argument("--since", type=int, default=None,
                        help="Only process essays numbered >= SINCE")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON summary")
    args = parser.parse_args()

    result = run_pipeline(
        dry_run=args.dry_run,
        since=args.since,
        report_only=args.report,
    )

    if args.json:
        print(json.dumps(result, indent=2))

    sys.exit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
