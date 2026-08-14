"""M3 Hook generation — multi-stage, evidence-informed pipeline (Phases 7-15).

The generator NEVER copies successful hooks. It extracts their underlying
structures (pattern extraction), then instantiates those patterns with the
user's topic via a deterministic template engine, filters hard, dedups by
embedding similarity, scores with configurable weights, optionally critiques
with an LLM (only when reasoning genuinely helps), mutates, and ranks.

Pipeline:
  STAGE A  candidates (deterministic patterns + optional LLM)
  STAGE B  deterministic quality filter
  STAGE C  novelty filter (embedding similarity vs corpus)
  STAGE D  HookScore (weighted, configurable)
  STAGE E  LLM critique (optional, graceful degradation)
  STAGE F  mutation
  STAGE G  final ranking -> ~12 hooks

Factuality: the engine NEVER invents figures, dates, names or events. Facts
must come from the user (topic string may carry "facts=" style annotations)
or be inherited from retrieved hooks' topics. Everything else is explicitly
tagged CREATIVE_FRAMING and flagged verification_required.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from miner.hook_dna import extract_dna
from miner.hook_retrieval import build_embedder, cosine, embed

# ------------------------------------------------------------------ modes

MODES = {
    "retention_optimized": {"devices": ["shocking_fact", "impossible_outcome",
                                        "curiosity_gap", "direct_question"],
                            "emotions": ["curiosity", "surprise"],
                            "weights": {"curiosity": 20, "specificity": 15,
                                        "stakes": 15, "novelty": 10,
                                        "clarity": 10, "open_loop": 15,
                                        "promise": 10, "pacing": 5}},
    "curiosity": {"devices": ["curiosity_gap", "mystery", "direct_question",
                              "pattern_interrupt"],
                  "emotions": ["curiosity"],
                  "weights": {"curiosity": 25, "specificity": 5, "stakes": 5,
                              "novelty": 15, "clarity": 10, "open_loop": 25,
                              "promise": 5, "pacing": 10}},
    "shock": {"devices": ["shocking_fact", "impossible_outcome",
                          "pattern_interrupt"],
              "emotions": ["surprise", "disbelief"],
              "weights": {"curiosity": 15, "specificity": 20, "stakes": 15,
                          "novelty": 15, "clarity": 5, "open_loop": 10,
                          "promise": 5, "pacing": 15}},
    "story": {"devices": ["story_medias_res", "confession", "result_first"],
              "emotions": ["anticipation", "curiosity"],
              "weights": {"curiosity": 15, "specificity": 10, "stakes": 10,
                          "novelty": 10, "clarity": 15, "open_loop": 15,
                          "promise": 10, "pacing": 15}},
    "investigation": {"devices": ["mystery", "result_first", "authority_based"],
                      "emotions": ["curiosity", "confusion"],
                      "weights": {"curiosity": 20, "specificity": 15,
                                  "stakes": 15, "novelty": 10, "clarity": 10,
                                  "open_loop": 15, "promise": 10, "pacing": 5}},
    "contrarian": {"devices": ["contrarian_claim", "contradiction"],
                   "emotions": ["surprise", "disbelief"],
                   "weights": {"curiosity": 20, "specificity": 10, "stakes": 15,
                               "novelty": 20, "clarity": 10, "open_loop": 15,
                               "promise": 5, "pacing": 5}},
    "money": {"devices": ["shocking_fact", "impossible_outcome", "warning"],
              "emotions": ["greed", "fear"],
              "weights": {"curiosity": 10, "specificity": 25, "stakes": 25,
                          "novelty": 10, "clarity": 10, "open_loop": 5,
                          "promise": 5, "pacing": 10}},
    "emotional": {"devices": ["confession", "story_medias_res", "identity_based"],
                  "emotions": ["fear", "hope", "anger"],
                  "weights": {"curiosity": 10, "specificity": 5, "stakes": 20,
                              "novelty": 10, "clarity": 15, "open_loop": 10,
                              "promise": 15, "pacing": 15}},
    "documentary": {"devices": ["authority_based", "result_first", "mystery"],
                    "emotions": ["curiosity", "anticipation"],
                    "weights": {"curiosity": 15, "specificity": 15, "stakes": 15,
                                "novelty": 10, "clarity": 15, "open_loop": 10,
                                "promise": 15, "pacing": 5}},
    "fast": {"devices": ["pattern_interrupt", "direct_question", "negative_opening"],
             "emotions": ["urgency", "curiosity"],
             "weights": {"curiosity": 20, "specificity": 10, "stakes": 15,
                         "novelty": 10, "clarity": 5, "open_loop": 15,
                         "promise": 5, "pacing": 20}},
    "authority": {"devices": ["authority_based", "warning", "prediction"],
                  "emotions": ["fear", "anticipation"],
                  "weights": {"curiosity": 10, "specificity": 15, "stakes": 20,
                              "novelty": 10, "clarity": 15, "open_loop": 10,
                              "promise": 10, "pacing": 10}},
    "mystery": {"devices": ["mystery", "curiosity_gap", "direct_question"],
                "emotions": ["curiosity", "confusion"],
                "weights": {"curiosity": 20, "specificity": 5, "stakes": 10,
                            "novelty": 15, "clarity": 10, "open_loop": 25,
                            "promise": 5, "pacing": 10}},
}

DEFAULT_WEIGHTS = MODES["retention_optimized"]["weights"]

# ------------------------------------------------------------ topic shaping

_VERB_ING = {"make": "making", "earn": "earning", "charge": "charging",
             "lose": "losing", "work": "working", "build": "building",
             "become": "becoming", "win": "winning", "grow": "growing",
             "sell": "selling", "raise": "raising", "cut": "cutting",
             "drop": "dropping", "take": "taking", "buy": "buying",
             "pay": "paying", "own": "owning", "run": "running",
             "spend": "spending", "save": "saving", "keep": "keeping",
             "made": "making", "earned": "earning", "charged": "charging",
             "lost": "losing", "worked": "working", "built": "building",
             "became": "becoming", "won": "winning", "grew": "growing",
             "sold": "selling", "raised": "raising", "cut": "cutting",
             "dropped": "dropping", "took": "taking", "bought": "buying",
             "paid": "paying", "owned": "owning", "ran": "running",
             "spent": "spending", "saved": "saving", "kept": "keeping"}

_TOPIC_Q = re.compile(
    r"^(why|how|what|who)\s+(?:does\s+|do\s+|did\s+)?(.+?)\s+"
    r"(makes?|earns?|charges?|loses?|works?|builds?|becomes?|wins?|grows?|"
    r"sells?|raises?|cuts?|drops?|takes?|buys?|pays?|owns?|runs?|spends?|"
    r"saves?|keeps?|became|made|earned|built|lost|won|grew|sold|raised|cut|"
    r"dropped|took|bought|paid|owned|ran|spent|saved|kept)\s+(.+)$", re.I)


_KEEP_VERBS = {"keep", "keeps", "kept"}  # catenative: "keep getting" -> "getting"


def nominal_topic(topic: str) -> str:
    """'Why Lamborghini makes so much money' -> 'lamborghini making so much
    money' so the topic slots grammatically into templates. Falls back to the
    raw topic (lowercased) when the shape is unrecognized."""
    m = _TOPIC_Q.match(topic.strip())
    if m:
        subj, verb, rest = m.group(2).strip(), m.group(3).lower(), m.group(4).strip()
        if verb in _KEEP_VERBS:
            # "keep getting more expensive" -> "getting more expensive"
            return f"{subj} {rest}".strip()
        # "makes" -> stem "make" before consulting the -ing map
        ing = (_VERB_ING.get(verb)
               or _VERB_ING.get(verb[:-1] if verb.endswith("s") else verb, verb))
        return f"{subj} {ing} {rest}".strip()
    return topic.strip().lower()


def _topic_slots(topic: str) -> tuple[str, str]:
    """(nominal form for embedding, question-friendly form)."""
    np_ = nominal_topic(topic)
    return np_, np_

PATTERNS = [
    # (human label, device tags used by mode filtering, templates)
    # expectation -> reversal -> unanswered why
    ("EXPECTATION → REVERSAL → UNANSWERED WHY",
     ("shocking_fact", "impossible_outcome", "contrarian_claim"),
     ["Everyone thinks {topic} works. Then the numbers stopped adding up. "
      "The question is why nobody saw it coming.",
      "Most people believe {topic} is solid. It is not. And the reason "
      "has stayed hidden for years."]),
    # specific outcome -> mystery
    ("SPECIFIC OUTCOME → MYSTERY",
     ("shocking_fact", "impossible_outcome", "curiosity_gap"),
     ["{topic} produced a fortune — and then quietly fell apart. "
      "What happened next is not what you expect.",
      "{topic} made its owners rich beyond imagination. Then, without "
      "warning, it was gone."]),
    # state -> contradiction -> stakes
    ("STATE → CONTRADICTION → STAKES",
     ("contradiction", "consequence_first"),
     ["{topic} looked like a sure thing. The contradiction at its center "
      "costs real money every single day.",
      "{topic} was supposed to be simple. It is not, and the price of "
      "getting it wrong is steep."]),
    # question -> curiosity gap
    ("QUESTION → CURIOSITY GAP",
     ("direct_question", "curiosity_gap", "mystery"),
     ["Why does {topic} work so well — and what breaks it?",
      "How does {topic} actually work? The answer is not what you "
      "were told."]),
    # shocking claim -> open loop
    ("CLAIM → OPEN LOOP",
     ("curiosity_gap", "mystery", "prediction"),
     ["The truth about {topic} is stranger than the headline.",
      "Nobody talks about what {topic} really does. There is a reason."]),
    # warning -> consequence
    ("WARNING → CONSEQUENCE",
     ("warning", "negative_opening", "authority_based"),
     ["Before you trust {topic}, understand what it is quietly doing.",
      "Never assume {topic} is safe. The consequences are real."]),
    # investigation promise
    ("INVESTIGATION PROMISE",
     ("story_medias_res", "mystery", "result_first"),
     ["I went looking for the real story behind {topic}. What I found "
      "changes how you should read it.",
      "The full story of {topic} has never been told properly. This is "
      "that story."]),
    # identity-based stakes
    ("IDENTITY → STAKES",
     ("identity_based",),
     ["If {topic} touches your money, you need to know this.",
      "Your future depends on understanding {topic} — and almost nobody "
      "does."]),
    # pattern interrupt
    ("PATTERN INTERRUPT",
     ("pattern_interrupt",),
     ["Wait. {topic} is not what you think it is.",
      "Stop. Before you make another decision about {topic}, hear this."]),
    # contrarian
    ("CONTRARIAN",
     ("contrarian_claim", "contradiction"),
     ["Everyone is wrong about {topic}. Here is the part nobody checks.",
      "The conventional wisdom on {topic} is backwards."]),
]

# patterns that require an explicit FACT slot (only used when facts provided)
FACT_PATTERNS = [
    ("FACT → REVERSAL",
     ["{topic} {fact}. Then everything changed.",
      "{topic} {fact} — and the fallout is still unfolding."]),
    ("FACT → UNANSWERED WHY",
     ["{topic} {fact}. Nobody could explain why.",
      "{topic} {fact}. The reason is still hidden."]),
    ("FACT → STAKES",
     ["{topic} {fact}. For everyone involved, the stakes are enormous."]),
]

# -------------------------------------------------------------- filters

GENERIC_WORDS = {"the", "this", "that", "you", "your", "it", "is", "are",
                 "was", "were", "has", "have", "had", "but", "and", "or",
                 "so", "then", "just", "really", "actually", "thing",
                 "things", "video", "story", "everyone", "nobody", "people",
                 "money", "business", "company"}

FAKE_URGENCY = re.compile(r"\b(now|today|immediately|hurry|act now|"
                          r"before it'?s too late|don'?t miss)\b", re.I)
CLICKBAIT_NO_PAYOFF = re.compile(r"\b(you won'?t believe|mind-blowing|"
                                 r"shocking truth|this will change)\b", re.I)


def _quality_filter(text: str, facts: list[str]) -> tuple[bool, str]:
    t = text.strip()
    if len(t) < 12:
        return False, "too short"
    if len(t) > 320:
        return False, "too long"
    if re.search(r"[A-Z]{4,}", t):
        return False, "shouty caps"
    if CLICKBAIT_NO_PAYOFF.search(t):
        return False, "clickbait without payoff"
    if FAKE_URGENCY.search(t) and "deadline" not in t.lower():
        return False, "fake urgency"
    # unsupported claims: numbers NOT backed by a user fact
    nums = re.findall(r"\$\s?[\d,]+[mbk]?|\d[\d,]*\s?(?:million|billion)", t, re.I)
    if nums and not facts:
        return False, "unsupported number claim"
    words = set(re.findall(r"[a-z]{3,}", t.lower()))
    generic = len(words & GENERIC_WORDS) / max(len(words), 1)
    if generic > 0.55:
        return False, "too generic"
    return True, "ok"


def _dedup(texts: list[str], threshold: float = 0.86) -> list[str]:
    """Near-duplicate removal on raw text (cheap pre-filter before embeddings)."""
    out = []
    for t in texts:
        if any(SequenceMatcher(None, t.lower(), o.lower()).ratio() > threshold
               for o in out):
            continue
        out.append(t)
    return out


# --------------------------------------------------------------- scoring

def hook_score(text: str, dna: dict, weights: dict | None = None) -> dict:
    """HookScore: weighted dimensions, configurable, learned later from
    actual performance (feedback loop). Each dimension 0..100."""
    w = weights or DEFAULT_WEIGHTS
    t = text.lower()

    # curiosity: question + curiosity mechanism present + open loop
    curiosity = (dna["open_loop"] * 40 + dna["has_question"] * 25
                 + (dna["curiosity_mechanism"] != "none") * 20 + 15)

    # specificity: numbers, dollars, entities, concrete outcomes
    specificity = dna["specificity_score"]

    # stakes: how many stake types + strongest type
    stakes = min(100, len(dna["stakes_types"]) * 20 + 20 * (dna["stakes_type"] != "none"))

    # novelty: placeholder — filled by the novelty engine in the pipeline
    novelty = 60.0

    # clarity: short sentences, no shouting, no nested hedging
    clarity = 100
    if len(text) > 200:
        clarity -= 20
    if len(re.findall(r",", text)) > 4:
        clarity -= 10
    if re.search(r"\b(i think|maybe|possibly|i guess|kind of|sort of)\b", t):
        clarity -= 15
    clarity = max(0, clarity)

    # open loop: question or unresolved mechanism
    open_loop = dna["open_loop"] * 95 + (dna["has_question"] * 5)

    # promise: promise type + explicit payoff words
    promise = (dna["promise_type"] != "none") * 55 + (
        bool(re.search(r"\b(show|explain|find out|learn|tell|see|uncover)\b", t))) * 45

    # pacing: words; hooks 8-40 words score best (spoken at ~150 wpm)
    wc = dna["word_count"]
    if 8 <= wc <= 40:
        pacing = 90
    elif 4 <= wc < 8 or 40 < wc <= 60:
        pacing = 65
    else:
        pacing = 40

    dims = {"curiosity": curiosity, "specificity": specificity, "stakes": stakes,
            "novelty": novelty, "clarity": clarity, "open_loop": open_loop,
            "promise": promise, "pacing": pacing}
    score = sum(dims[k] * w[k] for k in dims) / sum(w.values())
    return {"score": round(score, 1),
            "dims": {k: round(v, 1) for k, v in dims.items()}}


# ------------------------------------------------------------- factuality

_NUMBER_CLAIM = re.compile(
    r"\$\s?[\d,]+[mbk]?|\d[\d,]*\s?(?:million|billion)|"
    r"\d+(?:\.\d+)?%|\b20\d\d\b", re.I)
# capitalized word that is NOT sentence-initial (a name/entity, not "The")
_ENTITY_CLAIM = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-zA-Z]{2,}\b")
_CLAIM_STOP = {"The", "In", "On", "At", "If", "When", "Why", "How", "This",
               "That", "It", "They", "We", "You", "So", "But", "And", "Now",
               "Then", "There", "Here"}


def tag_factuality(text: str, facts: list[str], entities: list[str]) -> dict:
    """FACT vs INFERENCE vs CREATIVE_FRAMING per claim-bearing element.

    The engine never invents facts; any number/date/entity in the hook must
    trace back to a user fact or the topic string itself.

    Claims are matched with NON-capturing groups so the full number is seen
    ("500 million", not "million"); sentence-initial capitals ("The") are
    never treated as claims.
    """
    nums = set(_NUMBER_CLAIM.findall(text))
    ents = {e for e in _ENTITY_CLAIM.findall(text) if e not in _CLAIM_STOP}
    known = set(_NUMBER_CLAIM.findall(" ".join(facts))) | set(entities)
    unverified = sorted({c for c in (nums | ents) if c not in known})[:5]
    has_number_claim = bool(_NUMBER_CLAIM.search(text))
    return {
        "has_claims": has_number_claim,
        "verification_required": bool(unverified) and has_number_claim,
        "unverified_claims": unverified,
        "label": "FACT" if facts else ("CREATIVE_FRAMING" if not has_number_claim
                                       else "INFERENCE"),
    }


# ------------------------------------------------------------ multi-length

LENGTH_TARGETS = {  # seconds -> approximate spoken words at ~150 wpm
    3: 8, 5: 13, 8: 20, 12: 30, 15: 38, 20: 50, 30: 75,
}

EXPANDERS = [
    " The stakes here are enormous — and almost nobody sees them coming.",
    " The question is why nobody noticed sooner.",
    " What comes next is the part they never tell you.",
    " By the end, you will understand exactly how it works.",
]


def fit_length(text: str, target_words: int) -> str:
    """Fit a hook to a spoken-length target WITHOUT naive truncation.

    Short direction: drop the LAST sentence first (keep the interruptive
    opener), then drop the weakest clause; never cut mid-word.
    Long direction: append structured expanders (stakes/promise/loop) so
    longer versions are independently written, not padded.
    """
    if target_words <= 0:
        return text
    wc = len(text.split())
    if wc <= target_words:
        out = text.rstrip(" .")
        need = target_words - wc
        for exp in EXPANDERS:
            if need <= 0:
                break
            out += exp
            need -= len(exp.split())
        return out.strip()

    # shorten: drop last sentences until we fit, then trim words at a clause
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = sentences[:]
    while len(kept) > 1 and len(" ".join(kept).split()) > target_words:
        kept = kept[:-1]
    joined = " ".join(kept)
    if len(joined.split()) <= target_words:
        return joined
    words = joined.split()
    cut = []
    for w_ in words:
        if len(cut) + 1 > target_words:
            break
        cut.append(w_)
    return " ".join(cut)


# -------------------------------------------------------------- mutation

MUTATIONS = {
    "shocking": lambda t: _prepend(t, "You are not ready for this. "),
    "curious": lambda t: _prepend(t, "There is something you do not know. "),
    "confrontational": lambda t: _prepend(t, "Everyone is wrong about "),
    "cinematic": lambda t: _prepend(t, "It started like any other day. "),
    "natural": lambda t: _append(t, " Let me show you what I mean."),
    "shorter": lambda t: fit_length(t, 20),
    "faster": lambda t: _prepend(t, "Quick question: "),
    "documentary": lambda t: _prepend(t, "For decades, nobody talked about this. "),
    "story": lambda t: _prepend(t, "It began quietly. "),
    "contrarian": lambda t: _prepend(t, "Everything you know about this is wrong. "),
    "money": lambda t: _append(t, " It is costing people real money."),
    "investigative": lambda t: _prepend(t, "I spent months looking into this. "),
    "usa": lambda t: _append(t, " This is happening in America right now."),
}

MUTATION_ALIASES = {
    "more_shocking": "shocking", "more_curious": "curious",
    "more_emotional": "story", "more_confrontational": "confrontational",
    "more_cinematic": "cinematic", "more_natural": "natural",
    "shorter": "shorter", "faster": "faster", "more_documentary": "documentary",
    "more_story_driven": "story", "more_contrarian": "contrarian",
    "more_money_focused": "money", "more_investigative": "investigative",
    "more_usa_audience_native": "usa",
}


def _prepend(t: str, p: str) -> str:
    t2 = t[0].lower() + t[1:] if t and t[0].isupper() else t
    return p + t2


def _append(t: str, a: str) -> str:
    sep = "" if t.rstrip().endswith((".", "!", "?")) else "."
    return t.rstrip() + sep + a


def mutate(text: str, style: str) -> str:
    key = MUTATION_ALIASES.get(style, style)
    fn = MUTATIONS.get(key)
    return fn(text) if fn else text


# --------------------------------------------------------- main pipeline

# narrative atom -> pattern family index (which PATTERNS template to echo)
STRUCT_TO_FAMILY = {
    "REVERSAL": 0, "UNEXPECTED_OUTCOME": 0, "SHOCK": 0,
    "CONTRADICTION": 2,
    "QUESTION": 3,
    "OPEN_LOOP": 4, "CLAIM": 4, "MYSTERY": 4,
    "CONSEQUENCE": 5, "PROBLEM": 5,
    "PROMISE": 6, "INVESTIGATION": 6,
}


def _evidence_pattern_family(ev_struct: str | None) -> int:
    """Map the strongest evidence hook's structure to a pattern family.
    Only first-position atoms count — the opening is what the viewer sees."""
    if not ev_struct:
        return 0
    first = ev_struct.split(" → ")[0]
    return STRUCT_TO_FAMILY.get(first, 0)


def generate(conn, topic: str, mode: str = "retention_optimized",
             duration_target: int = 8, facts: list[str] | None = None,
             niche: str | None = None, top_k: int = 8,
             use_llm: bool = False, novelty_threshold: float = 0.72,
             candidates: int = 60, final_count: int = 12,
             corpus: list[str] | None = None,
             weights: dict | None = None,
             retrieval_weights: dict | None = None,
             evidence: list[dict] | None = None) -> dict:
    """Full generation pipeline. Returns structured JSON (Phase 22 format).

    corpus: full library hook texts (for novelty). evidence: pre-retrieved
    hooks (caller may pass to avoid a second DB scan). Both optional —
    when absent, generate() queries the library itself.
    """
    facts = facts or []
    mode_cfg = MODES.get(mode, MODES["retention_optimized"])
    w = weights or mode_cfg["weights"]
    topic_np = nominal_topic(topic)

    # --- retrieve evidence first: patterns are instantiated from what works
    from miner.hook_retrieval import retrieve
    if evidence is None:
        evidence = retrieve(conn, topic, niche=niche, top_k=top_k,
                            weights=retrieval_weights)
    if corpus is None:
        corpus = [r[0] for r in conn.execute(
            "SELECT hook_text FROM hook_library WHERE hook_text IS NOT NULL")]
    # derive DNA from the strongest evidence hook to bias pattern selection
    ev_dna = extract_dna(evidence[0]["hook_text"]) if evidence else extract_dna(topic)
    ev_struct = ev_dna["narrative_structure"] if evidence else None

    # --- novelty: ONE embedder + corpus vectors, shared across all stages
    from miner.hook_retrieval import SimIndex
    idx = SimIndex(corpus) if corpus else None
    ev_sims = {t: (idx.sims(t) if idx else []) for t in
               [e["hook_text"] for e in evidence]}

    # --- STAGE A: candidates
    cands: list[str] = []
    for struct, tags, templates in PATTERNS:
        if mode_cfg["devices"] and any(d in tags for d in mode_cfg["devices"]):
            for tpl in templates:
                cands.append(tpl.format(topic=topic_np))
    # evidence-driven pattern: echo the structure the best evidence actually uses
    if evidence and ev_struct:
        fam = _evidence_pattern_family(ev_struct)
        for tpl in PATTERNS[fam][2][:2]:
            cands.append(tpl.format(topic=topic_np))
    if facts:
        for struct, templates in FACT_PATTERNS:
            for tpl in templates:
                cands.append(tpl.format(topic=topic_np, fact=facts[0]))
    cands = _dedup(cands)

    # --- STAGE B: deterministic filter
    kept = [c for c in cands if _quality_filter(c, facts)[0]]

    # --- STAGE C: novelty vs corpus + evidence
    kept, nov_info = _novelty_filter(kept, idx, ev_sims, novelty_threshold)

    # --- STAGE D + G: score, rank, cut
    scored = []
    for c in kept[:candidates]:
        dna = extract_dna(c)
        s = hook_score(c, dna, w)
        s["dims"]["novelty"] = _novelty_dim(idx.sims(c) if idx and idx.n else None)
        s["score"] = round(
            sum(s["dims"][k] * w[k] for k in s["dims"]) / sum(w.values()), 1)
        scored.append({"text": c, "dna": dna, **s})

    # --- STAGE E: LLM critique (optional, never blocks)
    if use_llm:
        scored = _llm_critique(scored, topic, mode, evidence)

    # --- STAGE F: mutation pass — top 3 candidates get 2 mutations each
    final = []
    for s in sorted(scored, key=lambda x: -x["score"])[:min(3, len(scored))]:
        final.append(s)
        for style in ("shocking", "curious"):
            m = mutate(s["text"], style)
            if m != s["text"] and _quality_filter(m, facts)[0]:
                d = extract_dna(m)
                ms = hook_score(m, d, w)
                ms["dims"]["novelty"] = s["dims"]["novelty"]
                ms["score"] = round(
                    sum(ms["dims"][k] * w[k] for k in ms["dims"]) / sum(w.values()), 1)
                final.append({"text": m, "dna": d, **ms})

    # --- STAGE G: final ranking + evidence + multi-length + explanation
    final.sort(key=lambda x: -x["score"])
    ret_proj = _retention_projection(evidence)
    confidence = _confidence(evidence)
    hooks = []
    for i, s in enumerate(final[:final_count], 1):
        dna = s["dna"]
        fact = tag_factuality(s["text"], facts, dna.get("entities", []))
        hooks.append({
            "rank": i,
            "text": s["text"],
            "score": s["score"],
            "curiosity": s["dims"]["curiosity"],
            "specificity": s["dims"]["specificity"],
            "stakes": s["dims"]["stakes"],
            "novelty": s["dims"]["novelty"],
            "clarity": s["dims"]["clarity"],
            "open_loop": s["dims"]["open_loop"],
            "promise": s["dims"]["promise"],
            "retention_projection": ret_proj,
            "pattern": dna["narrative_structure"],
            "opening_device": dna["opening_device"],
            "curiosity_mechanism": dna["curiosity_mechanism"],
            "evidence_count": len(evidence),
            "confidence": confidence,
            "novelty_fallback": nov_info["fallback"],
            "verification_required": fact["verification_required"],
            "factuality": fact["label"],
            "variants": {
                str(sec): fit_length(s["text"], LENGTH_TARGETS.get(sec, 20))
                for sec in (3, 5, 8, 12, 15, 20, 30)
            } if i <= 5 else None,
            "why_it_works": _why_it_works(dna),
            "risks": _risks(fact, dna),
        })

    return {
        "topic": topic, "mode": mode, "duration_target": duration_target,
        "evidence_videos": [{"id": e["video_id"], "channel": e["channel"],
                             "text": e["hook_text"][:120],
                             "score": e["outlier_score"], "retention": e["retention_10s"]}
                            for e in evidence[:5]],
        "hooks": hooks,
    }


def _novelty_filter(texts: list[str], idx, evidence_sims: dict[str, list[float]],
                    threshold: float) -> tuple[list[str], dict]:
    """Filter candidates too close to the corpus. One shared embedder/vectors.

    Returns (kept, info). When everything is filtered, the fallback is the
    LEAST-similar candidates — not the first N, which would silently ship the
    worst offenders.
    """
    if idx is None or idx.n == 0:
        return texts, {"novelty_filtered": 0, "fallback": False}
    out, rej = [], []
    for t in texts:
        sims = idx.sims(t)
        too_close = any(s > threshold for s in sims) or \
                    any(s > threshold + 0.06
                        for s in evidence_sims.get(t, []))
        (rej if too_close else out).append((t, max(sims) if sims else 0.0))
    if out:
        return [t for t, _ in out], {"novelty_filtered": len(rej),
                                     "fallback": False}
    # all rejected: return the least-similar ones, honestly labeled
    rej.sort(key=lambda tq: tq[1])
    return [t for t, _ in rej[:2]], {"novelty_filtered": len(rej),
                                     "fallback": True}


def _novelty_dim(sims: list[float] | None) -> float:
    """0-100: how unlike the existing corpus is this hook?"""
    if not sims:
        return 50.0
    worst = max(sims)
    return round(100 * max(0.0, 1 - worst / 0.9), 1)


def _confidence(evidence: list[dict]) -> str:
    """Honest confidence from evidence DIVERSITY, not raw count.

    A count alone overstates confidence: 8 hooks from one channel are weaker
    than 8 hooks from five channels. High requires many videos across
    channels; anything below is 'low' or 'insufficient' — never fabricated.
    """
    n_videos = len({e["video_id"] for e in evidence})
    n_channels = len({e.get("channel") for e in evidence if e.get("channel")})
    if n_videos >= 15 and n_channels >= 4:
        return "high"
    if n_videos >= 8 and n_channels >= 2:
        return "medium"
    if n_videos >= 4:
        return "low"
    return "insufficient"


def _retention_projection(evidence: list[dict]) -> float | None:
    """Evidence-grounded retention estimate: median observed retention_10s
    (within-video z) of the retrieved evidence hooks. This is a projection
    from measured data, NOT a prediction derived from the hook score."""
    vals = sorted(e["retention_10s"] for e in evidence
                  if e.get("retention_10s") is not None)
    if not vals:
        return None
    return round(float(vals[len(vals) // 2]), 3)


def _why_it_works(dna: dict) -> list[str]:
    why = []
    if dna["opening_device"] and dna["opening_device"] != "plain_statement":
        why.append(f"Strong opening device ({dna['opening_device']})")
    if dna["open_loop"]:
        why.append("Creates an information gap")
    if dna["has_question"]:
        why.append("Direct question pulls an answer-seek")
    if dna["stakes_type"] != "none":
        why.append(f"Clear stakes ({dna['stakes_type']})")
    if dna["specificity_score"] >= 50:
        why.append("Specific and concrete")
    if dna["narrative_structure"] and "→" in dna["narrative_structure"]:
        why.append(f"Structured narrative ({dna['narrative_structure']})")
    if not why:
        why.append("Clean, direct statement of stakes")
    return why[:5]


def _risks(fact: dict, dna: dict) -> list[str]:
    risks = []
    if fact["verification_required"]:
        risks.append("Claim must be factually verified before publishing")
    if dna["word_count"] > 40:
        risks.append("May read long; tighten delivery")
    if not dna["open_loop"]:
        risks.append("No open loop — may lack curiosity pull")
    if dna["curiosity_mechanism"] == "none":
        risks.append("Generic framing; consider adding a specific number or date")
    return risks or ["Low risk — matches successful niche patterns"]


def _llm_critique(scored: list[dict], topic: str, mode: str,
                  evidence: list[dict]) -> list[dict]:
    """Optional LLM pass. Uses miner.llm's Claude provider; degrades silently."""
    try:
        from miner.llm import classify
    except Exception:
        return scored
    prompt = (
        "You are a YouTube hook critic. Below are candidate hooks for the "
        f"topic '{topic}' (mode: {mode}). For EACH, reply with a single line: "
        "RANK|HOOK_INDEX|SCORE_0_100|ONE_WORD_FLAW. Only critique wording, "
        "structure and curiosity — never invent facts.\n" +
        "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(scored))
    )
    out = classify(prompt, fallback="")
    if not out:
        return scored
    try:
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) >= 3 and parts[0].strip() == "RANK":
                idx = int(parts[1].strip())
                adj = float(parts[2].strip()) / 100.0
                if 0 <= idx < len(scored):
                    # blend: LLM opinion adjusts at most ±10 points
                    scored[idx]["score"] = round(
                        scored[idx]["score"] * 0.8 + adj * 100 * 0.2, 1)
    except (ValueError, IndexError):
        pass
    return scored