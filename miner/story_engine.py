"""Story Intelligence layer for video_engine.

This is additive: it does not modify the existing Shorts or long-form engines.
It turns a researched business topic into a stronger writing brief by combining
existing Hook DNA with long-form narrative constraints.

CPU/RAM design: stdlib + existing deterministic Hook DNA. Optional LLM is
remote; no local model is required.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from miner.hook_dna import extract_dna


@dataclass
class HookCandidate:
    text: str
    device: str
    score: float
    dna: dict[str, Any]
    reasons: list[str]
    warnings: list[str]


@dataclass
class StoryBlueprint:
    topic: str
    thesis: str
    central_question: str
    hook_candidates: list[dict[str, Any]]
    cold_open: dict[str, Any]
    narrative_arc: list[dict[str, Any]]
    retention_rules: list[str]
    evidence_rules: list[str]
    visual_contract: list[str]
    ending: dict[str, Any]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", text))


def _numbers(text: str) -> list[str]:
    return re.findall(r"(?:[$€£]\s*)?\d[\d,.]*(?:\s*(?:million|billion|trillion|thousand|%|[KMB]))?", text, re.I)


def _score_hook(text: str, facts: list[str]) -> HookCandidate:
    dna = extract_dna(text)
    low = text.lower()
    score = 0.0
    reasons: list[str] = []
    warnings: list[str] = []

    contradiction = bool(re.search(r"\b(but|yet|however|instead|despite|turns out|actually)\b", low))
    question = "?" in text
    numbers = bool(_numbers(text))
    proper = len(re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b", text)) > 0
    open_loop = bool(re.search(r"\b(why|how|what happened|the reason|the real|hidden|until|then)\b", low))
    generic = bool(re.search(r"\b(you won'?t believe|insane|crazy|shocking truth|let'?s dive|hey guys)\b", low))
    words = _word_count(text)

    if contradiction:
        score += 25; reasons.append("contradiction present")
    if open_loop:
        score += 20; reasons.append("unanswered question/open loop")
    if numbers:
        score += 15; reasons.append("specific evidence/number")
    if proper:
        score += 10; reasons.append("specific entity")
    if question:
        score += 8; reasons.append("explicit question")
    if 10 <= words <= 55:
        score += 12; reasons.append("cold-open length is usable")
    elif words > 75:
        warnings.append("hook is too long; tension may be diluted")
        score -= 10
    if generic:
        warnings.append("generic/clickbait language")
        score -= 25
    if not contradiction and not open_loop:
        warnings.append("no clear unresolved tension")
        score -= 15
    if not facts and numbers:
        warnings.append("number needs verification")

    return HookCandidate(text, "contradiction_first", max(0.0, min(100.0, score)), dna, reasons, warnings)


def rank_hooks(candidates: list[str], facts: list[str]) -> list[HookCandidate]:
    ranked = [_score_hook(x.strip(), facts) for x in candidates if x.strip()]
    return sorted(ranked, key=lambda x: x.score, reverse=True)


def build_blueprint(topic: str, thesis: str, facts: list[str], hooks: list[str]) -> StoryBlueprint:
    ranked = rank_hooks(hooks, facts)
    arc = [
        {"stage": "cold_open", "job": "Show an observable contradiction before explaining it.", "question": "What is strange here?"},
        {"stage": "evidence", "job": "Give the first concrete proof, not a pile of exposition.", "question": "Is the contradiction real?"},
        {"stage": "mechanism", "job": "Explain the incentive/economic mechanism that makes the contradiction rational.", "question": "How can this make sense?"},
        {"stage": "human_stakes", "job": "Translate the mechanism into a person, customer, worker or investor consequence.", "question": "Who actually pays or benefits?"},
        {"stage": "history", "job": "Show how the mechanism emerged and why it spread.", "question": "Where did this system come from?"},
        {"stage": "second_entity", "job": "Introduce a different company/industry/event that proves the pattern is structural.", "question": "Is this bigger than one example?"},
        {"stage": "reversal", "job": "Invalidate the viewer's working explanation with stronger evidence.", "question": "What did we misunderstand?"},
        {"stage": "escalation", "job": "Increase consequence, scale or stakes without simply increasing adjectives.", "question": "How far does this go?"},
        {"stage": "payoff", "job": "Reveal the mechanism in its clearest form.", "question": "What is the actual business logic?"},
        {"stage": "reframe", "job": "Return to the opening image/number and change its meaning.", "question": "What did the opening really mean?"},
        {"stage": "hard_stop", "job": "End immediately after the final insight; no generic outro.", "question": "What should remain unresolved in the viewer's mind?"},
    ]
    return StoryBlueprint(
        topic=topic,
        thesis=thesis,
        central_question=f"Why does {topic.lower()} work the way it does—and what is the hidden mechanism?",
        hook_candidates=[asdict(x) for x in ranked[:8]],
        cold_open={
            "architecture": [
                "0:00–3.5 visual/audio observation; no thesis dump",
                "3.5–10 evidence arrives one piece at a time",
                "10–18 tension compounds; do not resolve",
                "18–30 hook claim lands and opens the main question",
            ],
            "rule": "The opening earns the explanation. The viewer should understand what is strange before being told what it means.",
        },
        narrative_arc=arc,
        retention_rules=[
            "Every major section must answer an earlier question and create a useful next question.",
            "Use reversals: change the meaning of an earlier fact rather than merely adding another fact.",
            "Create a meaningful state change roughly every 30–90 seconds; never interpret this as a required cut rate.",
            "Introduce a new entity, mechanism, time period, comparison, evidence type or consequence when the current idea is exhausted.",
            "Numbers should change the argument, not decorate it.",
            "Delay the complete thesis until the viewer has enough evidence to care about it.",
            "Protect the final 8–10% for payoff/reframe; do not spend it on housekeeping.",
        ],
        evidence_rules=[
            "Never invent numbers, dates, quotes, legal claims or named events.",
            "Tag claims as OBSERVED, INFERRED or CREATIVE_FRAMING.",
            "Any unsupported quantitative claim becomes verification_required.",
            "A hook pattern is not evidence of the underlying business claim.",
        ],
        visual_contract=[
            "Visual intent must be explicit for every major narrative section.",
            "Prefer real B-roll, archival evidence, documents and meaningful charts before decorative animation.",
            "A visual may hold when the narration is developing an idea; change it when meaning changes, not on a stopwatch.",
            "Never use generic coin/money animation as a fallback for an unknown visual requirement.",
        ],
        ending={
            "structure": "opening motif → new interpretation → concise final insight → hard stop",
            "forbidden": ["like and subscribe outro", "summary dump", "new fact after payoff", "generic motivational ending"],
        },
    )


def render_markdown(bp: StoryBlueprint) -> str:
    lines = [f"# Story Blueprint — {bp.topic}", "", f"**Thesis:** {bp.thesis}", f"**Central question:** {bp.central_question}", "", "## Hook candidates", ""]
    for i, h in enumerate(bp.hook_candidates, 1):
        lines += [f"### {i}. {h['score']:.1f}/100", h["text"], f"- Reasons: {', '.join(h['reasons']) or 'none'}", f"- Warnings: {', '.join(h['warnings']) or 'none'}", ""]
    lines += ["## Cold open", "", json.dumps(bp.cold_open, indent=2), "", "## Narrative arc", "", "| Stage | Job | Question |", "|---|---|---|"]
    for x in bp.narrative_arc:
        lines.append(f"| {x['stage']} | {x['job']} | {x['question']} |")
    lines += ["", "## Retention rules", ""] + [f"- {x}" for x in bp.retention_rules]
    lines += ["", "## Evidence rules", ""] + [f"- {x}" for x in bp.evidence_rules]
    lines += ["", "## Visual contract", ""] + [f"- {x}" for x in bp.visual_contract]
    lines += ["", "## Ending", "", json.dumps(bp.ending, indent=2), ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a high-retention business-story blueprint without touching Shorts/LongForm engines.")
    ap.add_argument("topic")
    ap.add_argument("--thesis", required=True)
    ap.add_argument("--hook", action="append", default=[])
    ap.add_argument("--fact", action="append", default=[])
    ap.add_argument("--out", default="data/story_runs")
    args = ap.parse_args()
    bp = build_blueprint(args.topic, args.thesis, args.fact, args.hook)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-") or "story"
    (out / f"{stem}.json").write_text(json.dumps(asdict(bp), indent=2, ensure_ascii=False), encoding="utf-8")
    (out / f"{stem}.md").write_text(render_markdown(bp), encoding="utf-8")
    print(f"WROTE {out / (stem + '.json')}")
    print(f"WROTE {out / (stem + '.md')}")
    print(f"TOP HOOK {bp.hook_candidates[0]['score']:.1f}/100" if bp.hook_candidates else "NO HOOK CANDIDATES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
