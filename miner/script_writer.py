"""Production script writer for video_engine.

This module is intentionally separate from Shorts generation.  It turns a
research topic + verified facts into a long-form business-documentary writing
brief and, when an LLM is configured, a complete script with machine-readable
retention devices.

Design goals:
- long-form first; never use Shorts pacing rules for 10-30 minute stories
- evidence before hype; no invented numbers, dates, names, quotes or events
- contradiction/open-loop based hooks, not generic clickbait
- every act creates a question, answers an earlier question, and creates the
  next one
- explicit payoff/reversal map so video_engine can build visuals around it
- deterministic validation before a script is accepted
- JSON + Markdown output so video_engine can consume the same artifact
- CPU/RAM friendly: SQLite/stdlib for planning; LLM is remote when enabled

The system is honest about evidence.  A high score is not a promise of
virality; generated material is tagged OBSERVED / INFERRED / CREATIVE_FRAMING
and verification_required where appropriate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from config import load_settings, resolve_path


PROFILES: dict[str, dict[str, Any]] = {
    "longform_business": {
        "min_minutes": 8,
        "max_minutes": 35,
        "wpm": 165,
        "pause_factor": 1.12,
        "devices": [
            "cold_open", "contradiction", "specific_evidence", "new_entity",
            "reversal", "consequence", "number_spike", "open_loop",
            "payoff", "reframe", "hard_stop",
        ],
    },
    "documentary": {
        "min_minutes": 8,
        "max_minutes": 35,
        "wpm": 165,
        "pause_factor": 1.10,
        "devices": [
            "cold_open", "mystery", "evidence", "entity", "reversal",
            "stakes", "number_spike", "open_loop", "payoff", "reframe",
        ],
    },
}


@dataclass
class Act:
    id: str
    purpose: str
    question_opened: str
    question_answered: str
    device: str
    target_minutes: float
    reveal: str


@dataclass
class Validation:
    passed: bool
    score: float
    errors: list[str]
    warnings: list[str]


@dataclass
class ScriptBrief:
    topic: str
    profile: str
    target_minutes: float
    target_words: int
    hook_contract: dict[str, Any]
    retention_map: list[dict[str, Any]]
    acts: list[dict[str, Any]]
    writing_rules: list[str]
    evidence_rules: list[str]


def target_words(minutes: float, wpm: int = 165, pause_factor: float = 1.12) -> int:
    return round(minutes * wpm / pause_factor)


def _fmt_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(round(seconds % 60))
    if s == 60:
        m += 1
        s = 0
    return f"{m}:{s:02d}"


def _extract_numbers(text: str) -> list[str]:
    return re.findall(r"(?:\$|€|£)?\d[\d,.]*(?:%|[KMB]|\s+(?:million|billion|thousand))?", text, re.I)


def _fact_tokens(facts: list[str]) -> set[str]:
    out: set[str] = set()
    for f in facts:
        out.update(_extract_numbers(f))
        out.update(re.findall(r"\b[A-Z][A-Za-z0-9&.-]{2,}\b", f))
    return out


def build_retention_map(minutes: float) -> list[dict[str, Any]]:
    """Build a documentary retention curve rather than a Shorts beat grid."""
    total = minutes * 60
    # The supplied Real Return/Company Sells Nothing research used major
    # devices around 18%, 29%, 39%, then a later number/entity/reversal and a
    # 92% landing. Keep this as a flexible long-form scaffold, not a claim of
    # universal YouTube behavior.
    positions = [
        (0.00, "cold_open", "contradiction + named entity/number"),
        (0.18, "new_entity", "introduce the mechanism/term"),
        (0.29, "reversal", "invalidate the obvious explanation"),
        (0.39, "new_entity_reversal", "raise the scale with a second domain/entity"),
        (0.57, "number_spike", "largest clean quantitative reveal so far"),
        (0.70, "new_entity", "widen the story or connect the second system"),
        (0.82, "reversal", "law/market/strategy changes the meaning"),
        (0.92, "landing", "reframe the cold open"),
        (1.00, "hard_stop", "end immediately after the payoff"),
    ]
    result = []
    for frac, device, what in positions:
        result.append({"at_sec": round(total * frac, 1), "at": _fmt_time(total * frac), "device": device, "what": what})
    return result


def build_acts(minutes: float) -> list[Act]:
    # Scale acts with runtime. These are narrative functions, not forced beat
    # durations. Video_engine can subdivide each act after VO is written.
    total = minutes
    weights = [0.10, 0.14, 0.22, 0.20, 0.18, 0.10, 0.06]
    names = [
        ("cold_open", "Make the viewer understand the contradiction before explaining it."),
        ("stake", "Translate the abstract business model into a human/financial consequence."),
        ("origin", "Show where the mechanism came from and why it made economic sense."),
        ("escalation", "Introduce a second entity or industry that proves the mechanism is larger."),
        ("reversal", "Break the viewer's working explanation with evidence and a better model."),
        ("consequence", "Show what changed for customers, companies, regulators or markets."),
        ("landing", "Answer the opening question and reframe the first image/number."),
    ]
    questions = [
        "Why does this apparently irrational thing make economic sense?",
        "Who benefits, who pays, and what is the hidden trade-off?",
        "Where did the mechanism come from?",
        "Is this one company or a broader system?",
        "What explanation seemed right but turns out to be incomplete?",
        "What does the mechanism ultimately change?",
        "What was the real answer hiding inside the opening contradiction?",
    ]
    answer = [
        "The contradiction is the mechanism.",
        "The incentive structure creates the behavior.",
        "The historical origin explains why the model spread.",
        "A second example proves the pattern is structural.",
        "The reversal changes the meaning of the earlier evidence.",
        "The consequences make the business logic concrete.",
        "The opening image/number means something different now.",
    ]
    reveals = [
        "contradiction",
        "human stake",
        "historical mechanism",
        "new entity",
        "reversal",
        "largest consequence",
        "final reframe",
    ]
    devices = ["cold_open", "stakes", "new_entity", "reversal", "number_spike", "open_loop", "reframe"]
    return [Act(f"A{i+1}", names[i][0], questions[i], answer[i], devices[i], round(total * weights[i], 2), reveals[i]) for i in range(7)]


def build_brief(topic: str, facts: list[str], minutes: float, profile: str = "longform_business") -> ScriptBrief:
    cfg = PROFILES[profile]
    minutes = max(cfg["min_minutes"], min(cfg["max_minutes"], minutes))
    words = target_words(minutes, cfg["wpm"], cfg["pause_factor"])
    retention = build_retention_map(minutes)
    acts = build_acts(minutes)
    return ScriptBrief(
        topic=topic,
        profile=profile,
        target_minutes=minutes,
        target_words=words,
        hook_contract={
            "type": "contradiction_first_longform",
            "rule": "Do not explain the thesis immediately. Establish an observable contradiction, then earn the claim.",
            "cold_open_layers": [
                "visual_first_or_audio_first_observation",
                "evidence_arrives_one_piece_at_a_time",
                "hook_claim_lands_after_tension_has accumulated",
            ],
            "forbidden": ["generic greeting", "fake urgency", "empty superlative", "unsupported number", "premature thesis dump"],
        },
        retention_map=retention,
        acts=[asdict(a) for a in acts],
        writing_rules=[
            "Every section must answer one earlier question and open the next useful question.",
            "Use specific evidence before interpretation; never use adjectives as evidence.",
            "Prefer reversals over constant escalation: the meaning of an earlier fact should change.",
            "Introduce a new entity, mechanism, time period or comparison when the current idea has been exhausted.",
            "Numbers are events: give them clean space and explain why the number matters.",
            "Do not force a cut every 2 seconds. Long-form pacing is controlled by narrative change, not edit frequency.",
            "Write visual intent separately from narration so video_engine can source footage without rewriting the VO.",
            "Use short sentences around major reveals and longer sentences for explanation.",
            "End with a reframe of the opening, then hard stop. Do not append a generic outro.",
        ],
        evidence_rules=[
            "Numbers, dates, named people, companies, legal events and quotations require a supplied/retrieved source.",
            "If a claim cannot be traced, mark it verification_required instead of inventing a plausible detail.",
            "Separate OBSERVED evidence from INFERRED explanation and CREATIVE_FRAMING.",
            "Never turn a hook pattern into a factual claim merely because a similar hook performed well.",
        ],
    )


def build_prompt(brief: ScriptBrief, facts: list[str]) -> str:
    return f"""You are the senior writer for a high-retention finance/business documentary channel.
Write a {brief.target_minutes:.1f}-minute faceless YouTube documentary about:
{brief.topic}

TARGET: approximately {brief.target_words} narration words. Do NOT inflate word count with repetition.

VERIFIED FACTS PROVIDED BY THE RESEARCHER:
{chr(10).join('- ' + f for f in facts) if facts else '- No verified facts supplied. Do not invent any.'}

HOOK CONTRACT:
{json.dumps(brief.hook_contract, indent=2)}

RETENTION MAP:
{json.dumps(brief.retention_map, indent=2)}

ACTS:
{json.dumps(brief.acts, indent=2)}

WRITING RULES:
{chr(10).join('- ' + x for x in brief.writing_rules)}

EVIDENCE RULES:
{chr(10).join('- ' + x for x in brief.evidence_rules)}

OUTPUT EXACTLY these sections:
1. TITLE PACKAGE
2. COLD OPEN
3. STAKE
4. ACT I
5. ACT II
6. ACT III
7. ACT IV
8. ACT V
9. LANDING / REFRAME
10. SOURCE / VERIFICATION NOTES

For every narrative section include:
[VISUAL INTENT: ...]
NARRATION
[RETENTION DEVICE: ...]
[QUESTION OPENED: ...]
[QUESTION ANSWERED: ...]

Cold open requirement: do NOT dump the thesis in sentence one. Build tension through observation/evidence and let the hook claim land after the viewer understands the contradiction. The opening must still make sense with no visuals other than the described scene.

Do not use "guys", "let's dive in", "crazy", "insane", fake urgency, generic motivational language, or empty clickbait.
Do not copy a reference video's wording. Learn the structural principle and write original language.
"""


def _claude(prompt: str, settings: dict) -> str:
    cfg = settings["llm"]["claude"]
    key = os.environ.get(cfg["key_env"], "")
    if not key:
        raise RuntimeError(f"{cfg['key_env']} not set")
    max_tokens = int(settings.get("script_writer", {}).get("max_tokens", 12000))
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": cfg["model"], "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
        timeout=300,
    )
    r.raise_for_status()
    return "".join(x.get("text", "") for x in r.json().get("content", []))


def validate_script(text: str, facts: list[str], minutes: float) -> Validation:
    errors: list[str] = []
    warnings: list[str] = []
    low = text.lower()
    if len(text.strip()) < 1000:
        errors.append("script is too short to be a real long-form draft")
    if re.search(r"\b(you won'?t believe|mind[- ]blowing|shocking truth|act now)\b", low):
        errors.append("generic/clickbait phrasing detected")
    if low.count("let's dive") or low.count("hey guys"):
        errors.append("generic creator intro detected")
    fact_text = " ".join(facts)
    allowed_numbers = set(_extract_numbers(fact_text))
    for number in _extract_numbers(text):
        if number not in allowed_numbers:
            warnings.append(f"number may require verification: {number}")
    if "[visual intent:" not in low:
        errors.append("missing machine-readable visual intent blocks")
    if "retention device:" not in low:
        errors.append("missing retention-device annotations")
    if "landing / reframe" not in low and "reframe" not in low:
        warnings.append("no explicit reframe section detected")
    words = len(re.findall(r"\b[\w’'-]+\b", text))
    expected = target_words(minutes)
    ratio = words / max(expected, 1)
    if ratio < 0.55:
        warnings.append(f"draft is {ratio:.0%} of target narration volume")
    if ratio > 1.35:
        warnings.append(f"draft is {ratio:.0%} of target volume; check repetition")
    score = 100.0
    score -= 25 * len(errors)
    score -= 5 * len(warnings)
    return Validation(not errors, max(0.0, min(100.0, score)), errors, warnings)


def render_markdown(brief: ScriptBrief, script: str | None, validation: Validation) -> str:
    lines = [
        f"# {brief.topic}",
        "",
        f"**Profile:** `{brief.profile}`  ",
        f"**Target runtime:** {brief.target_minutes:.1f} min  ",
        f"**Target narration:** ~{brief.target_words} words  ",
        f"**Validation:** {validation.score:.1f}/100 — {'PASS' if validation.passed else 'FAIL'}",
        "",
        "## Retention map",
        "",
        "| Time | Device | Purpose |",
        "|---:|---|---|",
    ]
    for x in brief.retention_map:
        lines.append(f"| {x['at']} | {x['device']} | {x['what']} |")
    lines += ["", "## Act architecture", ""]
    for a in brief.acts:
        lines += [f"### {a['id']} — {a['purpose']}", f"- Opens: {a['question_opened']}", f"- Answers: {a['question_answered']}", f"- Device: `{a['device']}`", f"- Target: {a['target_minutes']:.2f} min", ""]
    lines += ["## Writing contract", ""]
    lines += [f"- {x}" for x in brief.writing_rules]
    lines += ["", "## Evidence contract", ""]
    lines += [f"- {x}" for x in brief.evidence_rules]
    if script:
        lines += ["", "---", "", "# SCRIPT", "", script]
    lines += ["", "---", "", "## QC", ""]
    lines += [f"- Score: **{validation.score:.1f}/100**", f"- Passed: **{validation.passed}**"]
    if validation.errors:
        lines += ["", "### Errors"] + [f"- {x}" for x in validation.errors]
    if validation.warnings:
        lines += ["", "### Warnings"] + [f"- {x}" for x in validation.warnings]
    return "\n".join(lines) + "\n"


def write_outputs(brief: ScriptBrief, script: str | None, validation: Validation, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"brief": asdict(brief), "script": script, "validation": asdict(validation), "schema_version": "1.0"}
    output.with_suffix(".json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(brief, script, validation), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Production long-form script writer for video_engine")
    ap.add_argument("topic")
    ap.add_argument("--minutes", type=float, default=20.0)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="longform_business")
    ap.add_argument("--fact", action="append", default=[], help="verified fact; repeat for multiple facts")
    ap.add_argument("--facts-file", default=None)
    ap.add_argument("--llm", action="store_true", help="generate the full prose draft with configured Claude")
    ap.add_argument("--out", default="data/script_runs/script")
    args = ap.parse_args(argv)

    facts = list(args.fact)
    if args.facts_file:
        facts.extend(x.strip() for x in Path(args.facts_file).read_text(encoding="utf-8").splitlines() if x.strip())

    brief = build_brief(args.topic, facts, args.minutes, args.profile)
    script = None
    if args.llm:
        settings = load_settings()
        script = _claude(build_prompt(brief, facts), settings)
    validation = validate_script(script or render_markdown(brief, None, Validation(True, 100, [], [])), facts, brief.target_minutes)
    out = Path(args.out)
    write_outputs(brief, script, validation, out)
    print(f"[script-writer] {out.with_suffix('.md')}")
    print(f"[script-writer] {out.with_suffix('.json')}")
    print(f"[script-writer] validation={validation.score:.1f}/100 passed={validation.passed}")
    return 0 if validation.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
