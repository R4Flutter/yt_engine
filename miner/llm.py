"""M3 Miner — pluggable LLM classification (Ollama local or Claude API, PLAN §3).

provider: 'ollama' | 'claude' | 'off'  (config/settings.yaml -> llm.provider)
Falls back to heuristic rules when off/unavailable so the pipeline never blocks.
"""
import json
import os
import re
import sys

import requests

from config import load_settings

TITLE_FORMULAS = {
    "curiosity_gap": "curiosity gap (unresolved question/tease)",
    "specific_number": "specific odd number or exact figure",
    "how_x": '"How X works/makes money"',
    "rise_fall": "rise-and-fall / collapse story",
    "scam_fraud": "scam/fraud/investigation",
    "listicle": "listicle / ranked",
    "mistake": "money mistake / warning",
    "question": "direct question",
    "other": "other",
}
HOOK_ARCHETYPES = {
    "cold_open_stakes": "cold open with stakes in media res",
    "bold_claim": "bold claim / shocking number",
    "question": "rhetorical question",
    "story": "storytelling cold open",
    "stat": "stat-driven tease",
    "other": "other",
}


def _ollama(settings, prompt: str) -> str:
    cfg = settings["llm"]["ollama"]
    r = requests.post(
        f"{cfg['base_url']}/api/generate",
        json={"model": cfg["model"], "prompt": prompt, "stream": False},
        timeout=cfg["timeout"],
    )
    r.raise_for_status()
    return r.json()["response"]


def _claude(settings, prompt: str) -> str:
    cfg = settings["llm"]["claude"]
    key = os.environ.get(cfg["key_env"], "")
    if not key:
        raise RuntimeError(f"{cfg['key_env']} not set")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": cfg["model"],
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


_availability = {"checked": False, "ok": False}


def _llm_available(settings: dict) -> bool:
    if not _availability["checked"]:
        try:
            _ollama(settings, "ping")
            _availability["ok"] = True
        except Exception:
            _availability["ok"] = False
            print("  [llm] ollama not running; using heuristic classification", file=sys.stderr)
        _availability["checked"] = True
    return _availability["ok"]


def classify(prompt: str, fallback: str) -> str:
    """Returns a clean one-line classification; heuristic fallback on failure."""
    settings = load_settings()
    provider = settings["llm"]["provider"]
    try:
        if provider == "ollama":
            if not _llm_available(settings):
                return fallback
            out = _ollama(settings, prompt)
        elif provider == "claude":
            out = _claude(settings, prompt)
        else:
            return fallback
    except Exception as e:
        print(f"  [llm] {provider} unavailable ({e}); using heuristic", file=sys.stderr)
        return fallback
    return re.sub(r"^.*?[:\-]?\s*", "", out.strip()[:80]) or fallback


def classify_title_formula(title: str) -> str:
    t = title.lower()
    if any(w in t for w in ("scam", "fraud", "ponzi", "con artist", "sued", "scheme")):
        return "scam_fraud"
    if any(w in t for w in ("how ", "how to", "the way")):
        return "how_x"
    if any(w in t for w in ("rise", "fall", "empire", "collapse", "bankrupt", "lost everyth", "downfall")):
        return "rise_fall"
    if re.search(r"\d+(\.\d+)?", t) and any(w in t for w in ("mistake", "regret", "warn", "stop")):
        return "mistake"
    if re.search(r"^what|^why|^is |\?", t):
        return "question"
    if re.search(r"#\d|\d (reasons|ways|things|lessons)", t):
        return "listicle"
    if re.search(r"\d+[.,]\d+|\$\d{2,}", t):
        return "specific_number"
    return "curiosity_gap"


def classify_hook_archetype(hook_text: str) -> str:
    h = hook_text.lower()
    if any(w in h for w in ("million", "billion", "thousand", "$", "percent", "%")):
        return "bold_claim"
    if re.search(r"^(imagine|in 20|the year|when|on a|it was)", h):
        return "story"
    if h.strip().endswith("?") or re.search(r"^what|^why|^how did", h):
        return "question"
    if re.search(r"^(i spent|my|we|this)", h):
        return "cold_open_stakes"
    return "stat"


def title_stats(title: str) -> dict:
    """Research-backed title features (PLAN §1, ML features)."""
    numbers = re.findall(r"\$?\d+[.,]?\d*[kmb]?", title, re.IGNORECASE)
    specific = any("." in n or any(d in n for d in (",", "k", "m", "b")) or (n.isdigit() and len(n) >= 4) for n in numbers)
    words = title.split()
    return {
        "len": len(title),
        "word_count": len(words),
        "has_number": bool(numbers),
        "number_is_specific": specific,
        "uppercase_ratio": round(sum(1 for c in title if c.isupper()) / max(len(title), 1), 3),
    }