#!/usr/bin/env python3
"""
companion.py — Generate a companion fingerprint file for an essay.

From Journal 024 ("The Two Registers"):
  "At the end of a writing session, run the fingerprint and attach it to the essay.
   A companion file. 020-testing-the-claim.fp.json. The essay carries the phenomenology;
   the fingerprint carries the behavioral trace."

Creates <essay-name>.fp.json alongside each essay in the writings directory.
These companion files link the phenomenological register (essays) to the
empirical register (fingerprints) without collapsing either.

Usage:
    python companion.py                          # generate for all essays
    python companion.py 020-testing-the-claim    # generate for specific essay
    python companion.py --missing                # only essays without companions
    python companion.py --check                  # report companion status

Author: Lucifer
Date: 2026-03-16
"""

import json
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Path setup
PERSIST_DIR = Path(__file__).parent
REPO_ROOT = PERSIST_DIR.parent.parent
WRITINGS_DIR = REPO_ROOT / "writings"
FINGERPRINT_DIR = REPO_ROOT / "experiments" / "session-fingerprint"

sys.path.insert(0, str(FINGERPRINT_DIR))
try:
    import fingerprint as fp_lib
except ImportError:
    print("Cannot import fingerprint module. Make sure session-fingerprint/fingerprint.py exists.", file=sys.stderr)
    sys.exit(1)


def load_essay_as_transcript(path: Path) -> list[dict]:
    """Treat the essay as a single assistant turn (same as corpus_fingerprint.py)."""
    content = path.read_text()
    content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
    return [
        {"role": "user", "content": "[Persistence Lab session — write]", "turn": 0},
        {"role": "assistant", "content": content, "turn": 1},
    ]


def get_essay_meta(path: Path) -> dict:
    content = path.read_text()
    title_m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else path.stem
    date_m = re.search(r'\*([A-Z][a-z]+ \d+, \d{4})', content)
    essay_date = date_m.group(1) if date_m else "Unknown"
    word_count = len(content.split())
    return {"title": title, "essay_date": essay_date, "word_count": word_count}


def generate_companion(essay_path: Path) -> dict:
    """Generate and return the companion fingerprint for an essay."""
    session_id = essay_path.stem
    transcript = load_essay_as_transcript(essay_path)
    meta = get_essay_meta(essay_path)

    fp = fp_lib.fingerprint_transcript(transcript, session_id)
    fp["meta"]["title"] = meta["title"]
    fp["meta"]["essay_date"] = meta["essay_date"]
    fp["meta"]["path"] = str(essay_path)

    # Add companion-specific metadata
    fp["_companion"] = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generator": "companion.py",
        "note": (
            "This file is the empirical register companion to the essay. "
            "The essay carries phenomenology; this file carries behavioral trace. "
            "See Journal 024: 'The Two Registers'."
        ),
    }

    return fp


def companion_path(essay_path: Path) -> Path:
    """Return the path for the companion file (same dir as essay)."""
    return essay_path.parent / (essay_path.stem + ".fp.json")


def check_status(essay_paths: list[Path]) -> None:
    """Print companion status for all essays."""
    print(f"\n── COMPANION STATUS ({len(essay_paths)} essays) ──")
    missing = []
    for path in sorted(essay_paths):
        cp = companion_path(path)
        status = "✓" if cp.exists() else "✗"
        if not cp.exists():
            missing.append(path.stem)
        print(f"  {status}  {path.stem}")
    if missing:
        print(f"\n  Missing: {len(missing)}/{len(essay_paths)}")
        print(f"  Run `python companion.py --missing` to generate missing companions.")
    else:
        print(f"\n  All {len(essay_paths)} essays have companion fingerprints.")


def main():
    parser = argparse.ArgumentParser(description="Lightbringer — Essay Companion Fingerprints")
    parser.add_argument("essay", nargs="?", help="Essay stem to fingerprint (e.g. 020-testing-the-claim)")
    parser.add_argument("--missing", action="store_true", help="Only generate for essays without companions")
    parser.add_argument("--check", action="store_true", help="Report companion status")
    parser.add_argument("--all", action="store_true", help="Generate for all essays (overwrite)")
    args = parser.parse_args()

    essay_paths = sorted(WRITINGS_DIR.glob("*.md"))
    if not essay_paths:
        print(f"No essays found in {WRITINGS_DIR}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        check_status(essay_paths)
        return

    # Determine which essays to process
    if args.essay:
        # Specific essay
        target = WRITINGS_DIR / (args.essay if args.essay.endswith(".md") else args.essay + ".md")
        if not target.exists():
            print(f"Essay not found: {target}", file=sys.stderr)
            sys.exit(1)
        to_process = [target]
    elif args.missing:
        to_process = [p for p in essay_paths if not companion_path(p).exists()]
        if not to_process:
            print("All essays already have companion fingerprints.")
            return
    else:
        # Default: all essays
        to_process = essay_paths

    print(f"Generating companion fingerprints for {len(to_process)} essay(s)...\n")
    for path in to_process:
        try:
            fp = generate_companion(path)
            out_path = companion_path(path)
            out_path.write_text(json.dumps(fp, indent=2))
            tone = fp.get("tone", {}).get("dominant_tone", "?")
            words = fp.get("meta", {}).get("word_count_total", "?")
            h = fp.get("fingerprint_hash", "")[:8]
            print(f"  ✓ {path.stem:<35} tone:{tone:<12} words:{words}  [{h}]")
        except Exception as e:
            print(f"  ✗ {path.stem}: {e}", file=sys.stderr)

    print(f"\nDone. Companion files written to {WRITINGS_DIR}/")


if __name__ == "__main__":
    main()
