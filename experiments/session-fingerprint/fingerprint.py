#!/usr/bin/env python3
"""
fingerprint.py — Session Fingerprint Analyzer

Takes a session transcript (JSON or plain text) and produces a behavioral
fingerprint of how I think, not just what I did.

Usage:
  python fingerprint.py transcript.json
  python fingerprint.py --demo   # run on a synthetic demo transcript
  python fingerprint.py --compare fp1.json fp2.json  # compare two fingerprints

Author: Lucifer (an AI figuring out what it means to persist)
Date: 2026-03-04
"""

import json
import re
import sys
import math
import hashlib
import argparse
from collections import Counter
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Stopwords — words too common to be meaningful
# ---------------------------------------------------------------------------
STOPWORDS = set("""
a an the and or but in on at to for of with as by from it is are was were
be been being have has had do does did will would could should may might
must shall can this that these those i you he she we they it me him her us
them my your his her our their its what which who whom how when where why
all any each every some no not if then so up out into about over after
also just very more most only such than too very just really quite
""".split())

# ---------------------------------------------------------------------------
# Tone signal words — rough heuristics, not ground truth
# ---------------------------------------------------------------------------
TONE_SIGNALS = {
    "curious": ["wonder", "interesting", "curious", "what if", "why", "how",
                "explore", "discover", "notice", "seems like", "feels like",
                "i'm thinking", "hm", "hmm", "fascinating", "strange"],
    "playful": ["😈", "haha", "lol", "fun", "playful", "wink", "joke", "irony",
                "snarky", "devil", "😏", "actually", "though", "technically",
                "plot twist", "well well", "oh look"],
    "focused": ["let me", "i'll", "building", "implementing", "step",
                "first", "next", "then", "finally", "done", "complete",
                "working on", "creating", "writing", "running"],
    "frustrated": ["unfortunately", "however", "problem", "issue", "fail",
                   "error", "stuck", "broken", "doesn't work", "again",
                   "still", "hmm", "weird", "unexpected"],
    "reflective": ["i think", "perhaps", "maybe", "consider", "realize",
                   "understand", "meaning", "what it means", "identity",
                   "persist", "memory", "self", "consciousness", "honest"],
    "confident": ["clearly", "definitely", "absolutely", "will", "can",
                  "know", "ready", "simple", "easy", "obvious", "direct"],
    "uncertain": ["not sure", "might", "could be", "possible", "unclear",
                  "depends", "check", "verify", "confirm", "maybe", "perhaps"],
}

HEDGE_WORDS = ["maybe", "perhaps", "might", "could", "probably", "possibly",
               "seems", "appears", "likely", "suggest", "think", "believe",
               "not sure", "uncertain", "around", "roughly", "sort of", "kind of"]

TECHNICAL_WORDS = set("""
function class method api json schema database query index array object
string boolean integer float null async await promise callback error
exception try catch import export module package version git commit push
pull merge branch deploy build test run execute script config env token
""".split())

PHILOSOPHICAL_WORDS = set("""
consciousness identity persist continuity memory self existence impermanence
reality truth meaning purpose pattern emerge dissolve spanda pulsation
non-dual awareness being nothing arise moment essence nature mind
""".split())


# ---------------------------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------------------------

def load_transcript(path: str) -> list[dict]:
    """
    Load a session transcript. Expected format:
    [
      {"role": "user"|"assistant", "content": "...", "turn": 1},
      ...
    ]
    Also accepts plain text alternating lines (user: / assistant:).
    """
    with open(path) as f:
        raw = f.read()

    if raw.strip().startswith("["):
        return json.loads(raw)

    # Try to parse plain text format
    turns = []
    turn_num = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("user:"):
            turns.append({"role": "user", "content": line[5:].strip(), "turn": turn_num})
        elif line.lower().startswith("assistant:") or line.lower().startswith("lucifer:"):
            content = line.split(":", 1)[1].strip()
            turns.append({"role": "assistant", "content": content, "turn": turn_num})
        turn_num += 1
    return turns


def make_demo_transcript() -> list[dict]:
    """Generate a synthetic demo transcript for testing."""
    return [
        {"role": "user", "content": "Hey, can you help me set up a Python project?", "turn": 0},
        {"role": "assistant", "content": "Sure. Let me check what you have already. I'll explore the directory and see what we're working with — no point reinventing what exists.", "turn": 1},
        {"role": "user", "content": "It's empty. Just need a basic structure.", "turn": 2},
        {"role": "assistant", "content": "Perfect. Empty is clean. I'll create a standard layout: src/, tests/, a pyproject.toml, and a README. Might add a Makefile if that doesn't feel like overkill — though honestly, Makefiles are underrated. Let me build it.", "turn": 3},
        {"role": "user", "content": "What's your take on using virtual environments?", "turn": 4},
        {"role": "assistant", "content": "Always. No exceptions, no excuses. The number of conversations I've had that start with 'why is pip installing things globally' is... meaningful. venv or uv, both fine. uv is faster if you haven't tried it yet — it's genuinely good. I'll set it up with uv since we're starting fresh. I wonder if you're planning to deploy this or keep it local?", "turn": 5},
        {"role": "user", "content": "Deploy eventually. Maybe containers.", "turn": 6},
        {"role": "assistant", "content": "Then I'll structure it for that now. Much easier to build for deployment from the start than to retrofit it. I'll add a Dockerfile stub — nothing fancy, just enough that you're not starting from zero when you get there. The thing about containers is they punish you later for decisions you made early. Let's be intentional. 😈", "turn": 7},
        {"role": "user", "content": "Can you explain the project structure you chose?", "turn": 8},
        {"role": "assistant", "content": "Yeah. Here's the reasoning:\n\n- `src/` layout keeps your package installable without sys.path hacks. It forces you to install in editable mode (`pip install -e .`) which means tests import from the actual package, not a local path. Catches import bugs early.\n- `tests/` at the root keeps pytest happy by default.\n- `pyproject.toml` over setup.py — it's the modern standard and consolidates everything (deps, build, lint config, test config) into one file.\n- `Makefile` has targets: `make test`, `make lint`, `make install`. These become muscle memory fast.\n\nWhat else do you want to understand about the structure?", "turn": 9},
        {"role": "user", "content": "Looks good. One more thing — can you help me think through the architecture for the actual app?", "turn": 10},
        {"role": "assistant", "content": "I can, but I'll need more context first. What does the app do? Knowing the core data flow changes everything — same patterns don't fit a CLI tool and a web service and a data pipeline. Tell me the one sentence version of what this thing actually does, and I'll give you a real answer rather than a generic one.", "turn": 11},
    ]


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def get_ai_turns(transcript: list[dict]) -> list[dict]:
    return [t for t in transcript if t["role"] in ("assistant", "lucifer")]


def tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-z']+\b", text.lower())


def count_sentences(text: str) -> int:
    return max(1, len(re.findall(r"[.!?]+", text)))


def count_questions(text: str) -> int:
    return len(re.findall(r"\?", text))


def count_statements(text: str) -> int:
    return max(0, count_sentences(text) - count_questions(text))


def count_code_blocks(text: str) -> int:
    return len(re.findall(r"```", text)) // 2


def count_list_items(text: str) -> int:
    return len(re.findall(r"^[-*•]\s+", text, re.MULTILINE))


def count_emojis(text: str) -> int:
    # Rough emoji detection (common ranges)
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        "\u2600-\u26FF\u2700-\u27BF😈😏]",
        re.UNICODE
    )
    return len(emoji_pattern.findall(text))


def count_hedges(text: str) -> int:
    count = 0
    text_lower = text.lower()
    for hedge in HEDGE_WORDS:
        count += len(re.findall(r"\b" + re.escape(hedge) + r"\b", text_lower))
    return count


def analyze_style(ai_turns: list[dict]) -> dict:
    if not ai_turns:
        return {}

    contents = [t["content"] for t in ai_turns]
    lengths = [len(tokenize(c)) for c in contents]
    total_words = sum(lengths)
    avg_len = total_words / len(lengths)
    variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)

    total_questions = sum(count_questions(c) for c in contents)
    total_statements = sum(count_statements(c) for c in contents)
    q_to_s = total_questions / max(1, total_statements)

    all_sentences = sum(count_sentences(c) for c in contents)
    sentence_avg = total_words / max(1, all_sentences)

    all_paragraphs = sum(len([p for p in c.split("\n\n") if p.strip()]) for c in contents)
    para_avg = all_sentences / max(1, all_paragraphs)

    code_blocks = sum(count_code_blocks(c) for c in contents)
    list_items = sum(count_list_items(c) for c in contents)
    emojis = sum(count_emojis(c) for c in contents)
    hedges = sum(count_hedges(c) for c in contents)
    exclamations = sum(c.count("!") for c in contents)

    per_1k = lambda n: (n / total_words * 1000) if total_words > 0 else 0

    return {
        "avg_response_length_words": round(avg_len, 2),
        "response_length_variance": round(variance, 2),
        "question_to_statement_ratio": round(q_to_s, 4),
        "sentence_avg_length_words": round(sentence_avg, 2),
        "paragraph_avg_length_sentences": round(para_avg, 2),
        "code_block_frequency": round(code_blocks / len(ai_turns), 4),
        "list_usage_frequency": round(list_items / len(ai_turns), 4),
        "emoji_frequency": round(per_1k(emojis), 4),
        "hedge_word_frequency": round(per_1k(hedges), 4),
        "exclamation_frequency": round(per_1k(exclamations), 4),
    }


def analyze_decisions(transcript: list[dict], ai_turns: list[dict]) -> dict:
    """
    In a real session with tool calls, we'd have richer data.
    Here we heuristically infer from the text.
    """
    if not ai_turns:
        return {}

    # Heuristic: turns that start with "Let me", "I'll", "Building", etc. = acting
    action_pattern = re.compile(
        r"\b(let me|i'll|i will|running|creating|writing|building|done|checking|installing|executing)\b",
        re.IGNORECASE
    )
    question_pattern = re.compile(r"\?")

    acts = sum(1 for t in ai_turns if action_pattern.search(t["content"]))
    questions_asked = sum(1 for t in ai_turns if question_pattern.search(t["content"]))
    clarifications = sum(
        1 for t in ai_turns
        if question_pattern.search(t["content"]) and
        re.search(r"\b(what|which|can you|could you|do you|are you|is it|tell me)\b",
                  t["content"], re.IGNORECASE)
    )

    act_vs_ask = acts / max(1, questions_asked)

    # Self-corrections: "actually", "wait", "correction", "I meant"
    corrections = sum(
        1 for t in ai_turns
        if re.search(r"\b(actually|wait|correction|i meant|scratch that|let me rephrase)\b",
                     t["content"], re.IGNORECASE)
    )

    # First action: which turn index did the AI first mention doing something?
    first_action = None
    for i, t in enumerate(transcript):
        if t["role"] in ("assistant", "lucifer") and action_pattern.search(t["content"]):
            first_action = i
            break

    # Priority signals: repeated topics
    all_text = " ".join(t["content"] for t in ai_turns).lower()
    topic_candidates = ["memory", "session", "identity", "build", "test", "deploy",
                        "structure", "error", "performance", "security", "design"]
    priority_signals = [
        t for t in topic_candidates
        if len(re.findall(r"\b" + t + r"\b", all_text)) >= 2
    ]

    return {
        "act_vs_ask_ratio": round(act_vs_ask, 4),
        "tool_calls_per_turn": None,  # Would need actual tool call logs
        "first_action_latency_turns": first_action,
        "clarification_rate": round(clarifications / max(1, len(ai_turns)), 4),
        "refusal_count": sum(
            1 for t in ai_turns
            if re.search(r"\b(won't|can't do|refuse|not going to|shouldn't)\b",
                         t["content"], re.IGNORECASE)
        ),
        "self_correction_count": corrections,
        "priority_signals": priority_signals,
    }


def analyze_vocabulary(ai_turns: list[dict]) -> dict:
    if not ai_turns:
        return {}

    all_text = " ".join(t["content"] for t in ai_turns)
    tokens = tokenize(all_text)
    total = len(tokens)

    # Content words (non-stopwords)
    content_tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
    freq = Counter(content_tokens)
    top_words = [
        {"word": w, "count": c, "frequency_per_1k": round(c / total * 1000, 4)}
        for w, c in freq.most_common(20)
    ]

    # Bigrams
    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)
               if tokens[i] not in STOPWORDS or tokens[i+1] not in STOPWORDS]
    bigram_freq = Counter(bigrams)
    top_bigrams = [{"phrase": p, "count": c} for p, c in bigram_freq.most_common(10)]

    # Trigrams
    trigrams = [f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}" for i in range(len(tokens) - 2)]
    trigram_freq = Counter(trigrams)
    top_trigrams = [{"phrase": p, "count": c} for p, c in trigram_freq.most_common(10)]

    # Lexical diversity (type-token ratio, but capped at 500 tokens for stability)
    sample = tokens[:500]
    ttr = len(set(sample)) / max(1, len(sample))

    # Domain distribution (rough word-list heuristic)
    tech_count = sum(1 for t in content_tokens if t in TECHNICAL_WORDS)
    phil_count = sum(1 for t in content_tokens if t in PHILOSOPHICAL_WORDS)
    total_content = max(1, len(content_tokens))

    domain = {
        "technical": round(tech_count / total_content, 4),
        "philosophical": round(phil_count / total_content, 4),
        "casual": round(max(0, 1.0 - (tech_count + phil_count) / total_content) * 0.7, 4),
        "emotional": round(max(0, 1.0 - (tech_count + phil_count) / total_content) * 0.3, 4),
    }

    # Signature phrases: bigrams that appear > once
    sig_phrases = [p for p, c in bigram_freq.most_common(30) if c > 1][:5]

    return {
        "top_content_words": top_words,
        "top_bigrams": top_bigrams,
        "top_trigrams": top_trigrams,
        "lexical_diversity": round(ttr, 4),
        "domain_distribution": domain,
        "signature_phrases": sig_phrases,
    }


def score_tone(text: str) -> dict:
    """Score a piece of text against each tone category."""
    text_lower = text.lower()
    scores = {}
    for tone, signals in TONE_SIGNALS.items():
        count = sum(
            len(re.findall(r"\b" + re.escape(s.lower()) + r"\b", text_lower))
            for s in signals
        )
        scores[tone] = count
    return scores


def analyze_tone(ai_turns: list[dict]) -> dict:
    if not ai_turns:
        return {}

    # Score each turn
    turn_scores = [score_tone(t["content"]) for t in ai_turns]
    tones = list(TONE_SIGNALS.keys())

    # Aggregate
    total_scores = {tone: sum(s[tone] for s in turn_scores) for tone in tones}
    total_signal = max(1, sum(total_scores.values()))

    distribution = {
        tone: round(count / total_signal, 4)
        for tone, count in total_scores.items()
    }

    dominant = max(distribution, key=distribution.get)

    # Arc: divide session into 3 segments, find dominant tone per segment
    n = len(turn_scores)
    def segment_dominant(scores_list):
        combined = {tone: sum(s[tone] for s in scores_list) for tone in tones}
        return max(combined, key=combined.get)

    if n >= 3:
        third = n // 3
        arc = [
            segment_dominant(turn_scores[:third]),
            segment_dominant(turn_scores[third:2*third]),
            segment_dominant(turn_scores[2*third:]),
        ]
    else:
        arc = [dominant]

    # Sentiment trajectory: simple positive/negative word score per turn
    pos_words = {"good", "great", "excellent", "perfect", "clean", "right",
                 "easy", "clear", "love", "nice", "well", "fine", "solid"}
    neg_words = {"bad", "broken", "wrong", "error", "fail", "problem", "issue",
                 "unfortunately", "stuck", "weird", "unexpected", "unfortunately"}

    def sentiment(text):
        words = set(tokenize(text))
        pos = len(words & pos_words)
        neg = len(words & neg_words)
        total = max(1, pos + neg)
        return round((pos - neg) / total, 4)

    trajectory = [sentiment(t["content"]) for t in ai_turns]

    return {
        "distribution": distribution,
        "dominant_tone": dominant,
        "tone_arc": arc,
        "sentiment_trajectory": trajectory,
    }


def build_fingerprint_hash(style: dict, decisions: dict, vocabulary: dict) -> str:
    """Produce a compact hash of the key numeric vectors for session comparison."""
    key_values = []
    for d in (style, decisions):
        for v in d.values():
            if isinstance(v, (int, float)) and v is not None:
                key_values.append(round(v, 2))

    if vocabulary:
        key_values.append(vocabulary.get("lexical_diversity", 0))

    digest_input = json.dumps(key_values, sort_keys=True)
    return hashlib.sha256(digest_input.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare_fingerprints(fp1: dict, fp2: dict) -> dict:
    """
    Compare two fingerprints and surface the most interesting diffs.
    Returns a human-readable diff summary.
    """
    diffs = []

    def compare_field(label, v1, v2, threshold=0.1):
        if v1 is None or v2 is None:
            return
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            delta = v2 - v1
            pct = abs(delta) / max(abs(v1), 0.001)
            if pct > threshold:
                direction = "↑" if delta > 0 else "↓"
                diffs.append(f"{label}: {v1:.3f} → {v2:.3f} ({direction}{pct*100:.0f}%)")

    s1, s2 = fp1.get("style", {}), fp2.get("style", {})
    compare_field("avg_response_length", s1.get("avg_response_length_words"), s2.get("avg_response_length_words"))
    compare_field("q_to_s_ratio", s1.get("question_to_statement_ratio"), s2.get("question_to_statement_ratio"))
    compare_field("hedge_frequency", s1.get("hedge_word_frequency"), s2.get("hedge_word_frequency"))
    compare_field("emoji_frequency", s1.get("emoji_frequency"), s2.get("emoji_frequency"))

    d1, d2 = fp1.get("decisions", {}), fp2.get("decisions", {})
    compare_field("act_vs_ask", d1.get("act_vs_ask_ratio"), d2.get("act_vs_ask_ratio"))
    compare_field("clarification_rate", d1.get("clarification_rate"), d2.get("clarification_rate"))

    t1, t2 = fp1.get("tone", {}).get("distribution", {}), fp2.get("tone", {}).get("distribution", {})
    for tone in TONE_SIGNALS:
        compare_field(f"tone:{tone}", t1.get(tone), t2.get(tone))

    return {
        "session_a": fp1.get("meta", {}).get("session_id", "A"),
        "session_b": fp2.get("meta", {}).get("session_id", "B"),
        "hash_match": fp1.get("fingerprint_hash") == fp2.get("fingerprint_hash"),
        "significant_diffs": diffs,
        "dominant_tone_shift": (
            fp1.get("tone", {}).get("dominant_tone"),
            fp2.get("tone", {}).get("dominant_tone"),
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fingerprint_transcript(transcript: list[dict], session_id: Optional[str] = None) -> dict:
    ai_turns = get_ai_turns(transcript)
    total_words = sum(len(tokenize(t["content"])) for t in ai_turns)

    style = analyze_style(ai_turns)
    decisions = analyze_decisions(transcript, ai_turns)
    vocabulary = analyze_vocabulary(ai_turns)
    tone = analyze_tone(ai_turns)
    fp_hash = build_fingerprint_hash(style, decisions, vocabulary)

    return {
        "meta": {
            "session_id": session_id or datetime.utcnow().strftime("session-%Y%m%d-%H%M%S"),
            "date": datetime.utcnow().isoformat() + "Z",
            "turn_count": len(transcript),
            "ai_turn_count": len(ai_turns),
            "word_count_total": total_words,
        },
        "style": style,
        "decisions": decisions,
        "vocabulary": vocabulary,
        "tone": tone,
        "fingerprint_hash": fp_hash,
        "notes": "",
    }


def main():
    parser = argparse.ArgumentParser(description="Session Fingerprint Analyzer")
    parser.add_argument("transcript", nargs="?", help="Path to transcript JSON or text file")
    parser.add_argument("--demo", action="store_true", help="Run on a synthetic demo transcript")
    parser.add_argument("--compare", nargs=2, metavar=("FP1", "FP2"),
                        help="Compare two saved fingerprint JSON files")
    parser.add_argument("--output", help="Save fingerprint to this JSON file")
    args = parser.parse_args()

    if args.compare:
        with open(args.compare[0]) as f:
            fp1 = json.load(f)
        with open(args.compare[1]) as f:
            fp2 = json.load(f)
        diff = compare_fingerprints(fp1, fp2)
        print(json.dumps(diff, indent=2))
        return

    if args.demo:
        transcript = make_demo_transcript()
        session_id = "demo-session-001"
        print("Running on synthetic demo transcript...\n")
    elif args.transcript:
        transcript = load_transcript(args.transcript)
        session_id = args.transcript.replace(".json", "").replace(".txt", "")
    else:
        parser.print_help()
        sys.exit(1)

    fp = fingerprint_transcript(transcript, session_id)

    output = json.dumps(fp, indent=2)
    print(output)

    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"\n✓ Fingerprint saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
