"""M3 Hook DNA — deterministic extraction of a hook's full structure.

A hook is NOT just text. This module turns raw hook text into a structured
representation at six levels:

    LEVEL 1  lexical     — numbers, dollars, percent, proper nouns, pacing
    LEVEL 2  semantic    — stakes, promise, specificity
    LEVEL 3  narrative   — state/contradiction/question structure
    LEVEL 4  psychological — curiosity mechanism, emotional mechanism
    LEVEL 5  temporal    — first_*_sec markers (filled by hook_beats.py)
    LEVEL 6  retention   — joined heatmap behavior (hook_retention.py)

Everything here is deterministic regex/lexicon (mirroring the alignment.py
philosophy): ~1 GB free RAM on this box, and these features need precision on
finance language, not a 50 MB NER model.

Usage (library only):
    from miner.hook_dna import extract_dna
    dna = extract_dna("This company was worth $40 billion. Then it collapsed.")
"""

from __future__ import annotations

import re

# ------------------------------------------------------------------ lexicons

CONTRADICT = re.compile(
    r"\b(but|however|yet|although|though|instead|despite|still|even so|"
    r"on the other hand|turns out|turned out|ended up|actually)\b", re.I)
QUESTION = re.compile(r"^((what|why|how|who|where|when|is|are|do|does|did|"
                      r"can|could|would|should|have|has|had)\b.*\?$)|.*\?\s*$", re.I)
NUMBER = re.compile(r"\$?[\d,]+(\.\d+)?\s?(million|billion|thousand|trillion|k|m|b)?", re.I)
SPELLED = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"million|billion|trillion)\b", re.I)
DOLLAR = re.compile(r"(\$\s?[\d,]+|\b\d[\d,]*\s?(dollars?|bucks)\b|\$[\d.]+\s?[mbk]?\b)", re.I)
PERCENT = re.compile(r"(\d+(\.\d+)?\s?%|\bpercent\b)", re.I)
DATE = re.compile(r"\b(19|20)\d{2}\b|\b(january|february|march|april|may|june|"
                  r"july|august|september|october|november|december)\b", re.I)
# proper-noun candidates: capitalized token that is not sentence-initial
PROPER = re.compile(r"(?<!^)(?<![.!?]\s)\b([A-Z][a-zA-Z]{2,})\b")
STOP_CAPS = {"The", "But", "And", "So", "It", "This", "That", "He", "She",
             "They", "We", "You", "In", "On", "At", "If", "When", "What",
             "Why", "How", "Now", "Then", "I", "There", "Here", "These",
             "Those", "After", "Before", "Because", "Despite", "Inside"}
ORG_HINT = re.compile(
    r"\b(inc|corp|corporation|company|bank|group|holdings|ventures|capital|"
    r"fund|llc|ltd|co\.?)\b", re.I)

# ------------------------------------------------------------ opening devices

OPENING_DEVICES = [
    ("pattern_interrupt", re.compile(
        r"^(wait|hold on|stop|pause|actually|here'?s the thing|listen|look|"
        r"guess what|imagine this)\b", re.I)),
    ("shocking_fact", re.compile(
        r"^(this (company|man|woman|startup|video|story|business|empire)|"
        r"a (company|man|woman|startup))\b.*\b(lost|made|worth|collapsed|built|"
        r"destroyed|bankrupt|billion|million)\b", re.I)),
    ("contrarian_claim", re.compile(
        r"^(everyone|everybody|nobody|no one|most people|they|we|the whole "
        r"world)\b.*\b(thinks?|thought|says?|said|believes?|told|knows?|"
        r"assumed)\b", re.I)),
    ("impossible_outcome", re.compile(
        r"\b(made|earned|lost|built|gained|turned|spent)\b.*\$\s?[\d.,]+\s?"
        r"(million|billion|thousand)?", re.I)),
    ("direct_question", QUESTION),
    ("curiosity_gap", re.compile(
        r"\b(but (nobody|no one|here'?s|wait|what|why)|the (real|actual|inside|"
        r"hidden|secret) (reason|story|truth|cause)|nobody (knows|saw|expected)|"
        r"what you don'?t know)\b", re.I)),
    ("negative_opening", re.compile(
        r"^(no|never|nothing|nobody|no one|without|stop|don'?t|i won'?t)\b", re.I)),
    ("positive_opening", re.compile(
        r"^(yes|here'?s|i found|we found|this is|introducing|the answer is)\b", re.I)),
    ("story_medias_res", re.compile(
        r"^(it was|i was|in 20\d\d|on a|when i|the day|a (quiet|cold|hot|dark|"
        r"rainy) (morning|night|afternoon)|back in)\b", re.I)),
    ("unusual_comparison", re.compile(
        r"\b(unlike|compared to|compared with|versus|vs\.?|like a|the difference"
        r" between)\b", re.I)),
    ("prediction", re.compile(
        r"\b(will|won'?t|is going to|going to (change|be|become|collapse|explode|"
        r"happen)|the future of)\b", re.I)),
    ("confession", re.compile(
        r"^(i (spent|lost|bought|sold|quit|started|tried|did|made|invested|"
        r"wasted|gave))\b", re.I)),
    ("warning", re.compile(
        r"^(don'?t|never|warning|careful|before you|stop doing|this is your "
        r"sign)\b", re.I)),
    ("challenge", re.compile(
        r"\b(i bet|i dare|try to|challenge|can you|think you know)\b", re.I)),
    ("mystery", re.compile(
        r"\b(mystery|mysterious|nobody (knows|understands)|unknown|secret|hidden"
        r"|unexplained)\b", re.I)),
    ("contradiction", CONTRADICT),
    ("consequence_first", re.compile(
        r"^(because|which (is why|means)|that'?s why|as a result|so when)\b", re.I)),
    ("result_first", re.compile(
        r"^(the (result|outcome|end|aftermath)|after (years|months|decades|it "
        r"all)|what happened)\b", re.I)),
    ("identity_based", re.compile(
        r"\b(your (money|business|career|life|future|family|retirement)|if "
        r"you'?re a|you could be)\b", re.I)),
    ("authority_based", re.compile(
        r"\b(the (government|fed|federal|sec|ftc|court|ceo|founder|billionaire|"
        r"central bank|treasury|world bank))\b", re.I)),
]

# ---------------------------------------------------------- curiosity gaps

CURIOSITY = [
    ("information_gap", re.compile(
        r"\b(what you don'?t know|hidden|secret|unknown|nobody knows|don'?t "
        r"know|not what you think|didn'?t tell)\b", re.I)),
    ("contradiction", CONTRADICT),
    ("unanswered_why", re.compile(
        r"\bwhy\b(?![^.!?]{0,60}\bbecause\b)", re.I)),
    ("hidden_cause", re.compile(
        r"\b(behind|underneath|underlying|root cause|the cause|because of|"
        r"isn'?t what it seems)\b", re.I)),
    ("hidden_consequence", re.compile(
        r"\b(what (happened|comes next|followed)|the (aftermath|consequence|"
        r"fallout|price)|then (this|what))\b", re.I)),
    ("incomplete_story", re.compile(
        r"\b(but|until|before|not yet|still)\b", re.I)),
    ("missing_identity", re.compile(
        r"\b(someone|somebody|a man|a woman|the person|who (was|is) the|"
        r"the mystery (man|woman|person))\b", re.I)),
    ("unexpected_result", re.compile(
        r"\b(unexpectedly|surprisingly|turned out|ended up|against all odds|"
        r"somehow|out of nowhere)\b", re.I)),
    ("reversal", re.compile(
        r"\b(reversed|flipped|turned (out|around)|instead of|the opposite|"
        r"everything changed|no longer)\b", re.I)),
    ("forbidden_knowledge", re.compile(
        r"\b(banned|forbidden|illegal|never told|don'?t want you to know|won'?t "
        r"tell you|not allowed to say)\b", re.I)),
    ("secret_mechanism", re.compile(
        r"\b(secret|hidden|under the hood|how it actually|the real (reason|"
        r"mechanism|secret|story))\b", re.I)),
    ("comparison_gap", re.compile(
        r"\b(unlike|compared to|versus|vs\.?|the difference between|whereas)\b", re.I)),
    ("future_uncertainty", re.compile(
        r"\b(what'?s next|will it (last|survive|happen)|what happens (now|next)|"
        r"is it over|the future of)\b", re.I)),
]

# ------------------------------------------------------------- emotions

EMOTIONS = [
    ("surprise", re.compile(
        r"\b(shocking|surpris|unexpected|stunned|unbelievable|incredible|"
        r"nobody saw|came out of nowhere|blew my mind|insane)\b", re.I)),
    ("fear", re.compile(
        r"\b(fear|scared|afraid|terrifying|nightmare|worst|danger|risk|panic|"
        r"crash|collapse|bankrupt|destroyed|lost everything|wipe out)\b", re.I)),
    ("greed", re.compile(
        r"\b(money|billion|million|profit|fortune|made|earned|worth|rich|"
        r"wealth|windfall|$)\b", re.I)),
    ("curiosity", re.compile(
        r"\b(why|how|secret|hidden|unknown|mystery|nobody knows|the truth)\b", re.I)),
    ("anger", re.compile(
        r"\b(angry|outrage|outraged|furious|scam|fraud|stole|cheated|looted|"
        r"ripped off|unfair|corrupt|lies?|lied)\b", re.I)),
    ("admiration", re.compile(
        r"\b(genius|brilliant|legend|masterpiece|incredible|amazing|greatest|"
        r"mastermind)\b", re.I)),
    ("disbelief", re.compile(
        r"\b(unbelievable|can'?t believe|nobody believed|impossible|no way|"
        r"how did they|insane)\b", re.I)),
    ("urgency", re.compile(
        r"\b(now|today|immediately|before it'?s too late|deadline|fast|quickly|"
        r"the clock|right now)\b", re.I)),
    ("envy", re.compile(
        r"\b(jealous|envy|wish|imagine having|you could have|they had)\b", re.I)),
    ("anticipation", re.compile(
        r"\b(about to|is going to|coming next|wait until|you won'?t believe|"
        r"the moment)\b", re.I)),
    ("confusion", re.compile(
        r"\b(confus|don'?t understand|how did|why would|nobody understands|"
        r"doesn'?t make sense|doesn'?t add up)\b", re.I)),
    ("hope", re.compile(
        r"\b(hope|promise|could be|potential|dream|the future|recover|"
        r"turnaround|second chance)\b", re.I)),
]

# ---------------------------------------------------------------- stakes

STAKES = [
    ("money", re.compile(
        r"\$|dollar|billion|million|thousand|worth|price|cost|fee|revenue|"
        r"profit|salary|debt|wealth|net worth", re.I)),
    ("time", re.compile(
        r"\b(years|decades|months|days|hours|overnight|in just|long road|"
        r"wasted years)\b", re.I)),
    ("status", re.compile(
        r"\b(status|prestige|famous|celebrity|reputation|respect|credibility|"
        r"image|legacy)\b", re.I)),
    ("reputation", re.compile(
        r"\b(reputation|credibility|trust|trusted|ruined|shame|embarrass|"
        r"exposed|scandal|fraud)\b", re.I)),
    ("survival", re.compile(
        r"\b(survive|survival|bankrupt|collapse|destroyed|failed|death|die|"
        r"kill|crash|wipe out|end of)\b", re.I)),
    ("business", re.compile(
        r"\b(business|company|startup|entrepreneur|merger|acquisition|ipo|"
        r"quarterly|earnings|shareholder|market cap|valuation)\b", re.I)),
    ("career", re.compile(
        r"\b(career|job|fired|quit|promotion|salary|boss|interview|resign|"
        r"hired|laid off)\b", re.I)),
    ("opportunity", re.compile(
        r"\b(opportunity|chance|window|shot|once in a lifetime|potential|"
        r"missed out|could have)\b", re.I)),
    ("loss", re.compile(
        r"\b(lost|losing|lose|gone|wiped|vanished|plunged|slashed|cut|"
        r"down from|fell)\b", re.I)),
    ("risk", re.compile(
        r"\b(risk|risky|gamble|bet|danger|dangerous|speculative|volatile|"
        r"uncertain|bet the)\b", re.I)),
    ("identity", re.compile(
        r"\b(your (money|life|future|business|career|family)|you could be|"
        r"if you'?re a)\b", re.I)),
]

# ---------------------------------------------------------------- promises

PROMISES = [
    ("explanation", re.compile(
        r"\b(explain|here'?s how|how it works|the reason|why it|how .{0,40} "
        r"(works|makes|built|became))\b", re.I)),
    ("reveal", re.compile(
        r"\b(reveal|the truth|what really|inside|the real story|exposed|finally|"
        r"the untold)\b", re.I)),
    ("transformation", re.compile(
        r"\b(turn|become|transform|change your|go from|make you|turn you into)"
        r"\b", re.I)),
    ("answer", re.compile(
        r"\b(answer|the answer|here'?s what|i'?ll show|let me show|this is "
        r"why)\b", re.I)),
    ("investigation", re.compile(
        r"\b(investigat|dig into|uncover|the story behind|what happened to|"
        r"where .* went|the rise and fall)\b", re.I)),
    ("lesson", re.compile(
        r"\b(lesson|learn|mistake|what i learned|what to do|how to|never do)"
        r"\b", re.I)),
    ("prediction", re.compile(
        r"\b(predict|will (happen|last|survive|change)|what'?s next|the future "
        r"of|is going to)\b", re.I)),
    ("comparison", re.compile(
        r"\b(vs|versus|compared|difference between|side by side|which is "
        r"better)\b", re.I)),
]

# --------------------------------------------------- narrative structure atoms

NARRATIVE = [
    ("STATE", re.compile(
        r"\b(was worth|had|is|are|everyone thought|it was|there was|used to "
        r"be|started as|began as)\b", re.I)),
    ("CONTRADICTION", re.compile(r"\b(but|however|yet|although|though|despite"
                                 r"|instead|even so)\b", re.I)),
    ("REVERSAL", re.compile(
        r"\b(turned out|ended up|reversed|flipped|unexpectedly|surprisingly|"
        r"against all odds|came back|made a fortune|collapsed)\b", re.I)),
    ("QUESTION", QUESTION),
    ("STAKES", re.compile(
        r"\$|billion|million|thousand|lost|losing|bankrupt|collapsed|destroyed|"
        r"career|sued|fined", re.I)),
    ("SHOCK", re.compile(
        r"\b(\$[\d,]+|\d[\d,]*\s?(million|billion)|shocking|unbelievable|"
        r"insane)\b", re.I)),
    ("CLAIM", re.compile(
        r"\b(the (truth|real story|actual reason|inside story)|i (found|"
        r"discovered|spent|investigated)|nobody (knows|saw|expected))\b", re.I)),
    ("PROBLEM", re.compile(
        r"\b(problem|broke|broken|failed|failure|wrong|mistake|flaw|trouble)"
        r"\b", re.I)),
    ("CONSEQUENCE", re.compile(
        r"\b(because|which meant|which is why|as a result|so then|that'?s why)"
        r"\b", re.I)),
    ("PROMISE", re.compile(
        r"\b(here'?s how|let me show|in this video|by the end|you'?ll (see|"
        r"learn|understand)|i'?ll (show|explain|tell))\b", re.I)),
    ("MYSTERY", re.compile(
        r"\b(secret|hidden|unknown|mystery|nobody (knows|understands)|"
        r"unexplained)\b", re.I)),
    ("UNEXPECTED_OUTCOME", re.compile(
        r"\b(unexpected|surprisingly|against all odds|out of nowhere|turned "
        r"out|ended up)\b", re.I)),
    ("OPEN_LOOP", re.compile(
        r"\?|but (nobody|no one)|what (happened|comes next)|the (reason|truth|"
        r"story) (behind|is)", re.I)),
]

# --------------------------------------------------------- specificity hints

CONCRETE_OUTCOME = re.compile(
    r"\b(bankrupt|billionaire|collapsed|made .{0,12}(million|billion)|sold|"
    r"bought|fined|sued|lost .{0,12}(million|billion)|acquired|merged|went "
    r"public|ipo)\b", re.I)


# ---------------------------------------------------------------- extraction

def _first_match(patterns, text: str) -> str | None:
    """First pattern that matches, in declaration order (deterministic)."""
    for name, rx in patterns:
        if rx.search(text):
            return name
    return None


def _all_matches(patterns, text: str) -> list[str]:
    return [name for name, rx in patterns if rx.search(text)]


def _specific_numbers(text: str) -> int:
    """Count numbers that read as REAL, not marketing round numbers.

    $10,427 is specific; $10,000 and $40 billion are round estimates.
    Aligned with alignment.py's ROUND_NUM logic.
    """
    hits = 0
    for m in NUMBER.finditer(text):
        raw = m.group(0).replace("$", "").strip()
        bare = raw.replace(",", "")
        is_round = (
            bool(re.search(r"(,0{2,3}|\.0+|0{3})$", raw))       # 10,000 / 1,000 / 1000
            or bool(re.search(r"\b(ten|hundred|thousand|million|"
                              r"billion|trillion)\b", raw))
            or bool(re.search(r"[kmb]$", bare, re.I))           # 40m / 10k
        )
        if not is_round:
            hits += 1
    return hits


def extract_dna(text: str) -> dict:
    """Full Hook DNA for one hook. Pure deterministic — no LLM, no IO.

    Returns a flat dict of string/float/int fields (JSON-serializable).
    """
    t = text.strip()
    if not t:
        return {}
    words = t.split()
    wc = len(words)

    proper = {m for m in PROPER.findall(t) if m not in STOP_CAPS}
    entities = sorted(proper)
    orgs = [e for e in entities if ORG_HINT.search(t)]
    numbers = NUMBER.findall(t) if re.search(r"\d", t) else []

    # --- LEVEL 1 lexical
    lex = {
        "word_count": wc,
        "has_number": int(bool(re.search(r"\d", t) or SPELLED.search(t))),
        "specific_number_count": _specific_numbers(t),
        "has_dollar": int(bool(DOLLAR.search(t))),
        "has_percent": int(bool(PERCENT.search(t))),
        "has_date": int(bool(DATE.search(t))),
        "entity_count": len(entities),
        "company_count": len(orgs),
        "first_sentence_len": len(t.split(".")[0].split()) if "." in t else wc,
        "starts_with_question": int(bool(re.match(r"^(what|why|how|who|is|"
                                                  r"are|do|does|did|can|would)\b", t))),
    }

    # --- LEVEL 2-4 psychology
    opening = _first_match(OPENING_DEVICES, t) or "plain_statement"
    curiosity = _first_match(CURIOSITY, t) or "none"
    emotion = _first_match(EMOTIONS, t) or "neutral"
    stakes = _first_match(STAKES, t) or "none"
    promise = _first_match(PROMISES, t) or "none"
    all_emotions = _all_matches(EMOTIONS, t)
    all_stakes = _all_matches(STAKES, t)

    # --- LEVEL 3 narrative structure: order of atoms as they appear
    seen: dict[str, int] = {}
    for name, rx in NARRATIVE:
        m = rx.search(t)
        if m:
            pos = m.start()
            if name not in seen:
                seen[name] = pos
    structure = [n for n, _ in sorted(seen.items(), key=lambda kv: kv[1])]
    if not structure:
        structure = ["STATEMENT"]

    # --- open loop: does the hook leave an unanswered variable?
    has_question = bool(QUESTION.search(t))
    open_loop = has_question or bool(re.search(
        r"\b(but|nobody knows|the (reason|truth|story|cause) (behind|is)|"
        r"what (happened|comes next)|wait|yet)\b", t))
    if not open_loop and curiosity in (
        "information_gap", "unanswered_why", "hidden_cause",
        "hidden_consequence", "missing_identity", "future_uncertainty"):
        open_loop = True

    # --- concrete outcome (evidence the hook delivers specifics)
    concrete = bool(CONCRETE_OUTCOME.search(t))

    return {
        **lex,
        "opening_device": opening,
        "curiosity_mechanism": curiosity,
        "emotional_mechanism": emotion,
        "emotions": all_emotions,
        "stakes_type": stakes,
        "stakes_types": all_stakes,
        "promise_type": promise,
        "narrative_structure": " → ".join(structure),
        "open_loop": int(open_loop),
        "has_question": int(has_question),
        "specificity_score": min(100, (
            (lex["specific_number_count"] > 0) * 25 +
            lex["has_dollar"] * 20 +
            lex["has_percent"] * 10 +
            (lex["entity_count"] > 0) * 20 +
            lex["company_count"] * 15 +
            concrete * 10)),
        "concrete_outcome": int(concrete),
        "entities": entities,
        "companies": orgs,
    }


# -------------------------------------------------------------- archetypes

ARCHETYPE_BY_OPENING = {
    "shocking_fact": "bold_claim",
    "contrarian_claim": "bold_claim",
    "impossible_outcome": "bold_claim",
    "direct_question": "question",
    "curiosity_gap": "curiosity",
    "story_medias_res": "story",
    "confession": "cold_open_stakes",
    "consequence_first": "cold_open_stakes",
    "result_first": "result_first",
    "warning": "warning",
    "mystery": "mystery",
    "contradiction": "contradiction",
    "unusual_comparison": "comparison",
    "prediction": "prediction",
    "pattern_interrupt": "pattern_interrupt",
    "negative_opening": "negative",
    "positive_opening": "positive",
    "identity_based": "identity",
    "authority_based": "authority",
    "challenge": "challenge",
}

# Backwards compatibility with the 6 archetypes the DB already uses.
LEGACY_ARCHETYPES = {
    "bold_claim": "bold_claim", "question": "question", "story": "story",
    "cold_open_stakes": "cold_open_stakes", "curiosity": "stat",
    "result_first": "other", "warning": "other", "mystery": "other",
    "contradiction": "other", "comparison": "other", "prediction": "other",
    "pattern_interrupt": "other", "negative": "other", "positive": "other",
    "identity": "other", "authority": "other", "challenge": "other",
}


def archetype(dna: dict) -> str:
    """Fine-grained archetype from DNA; maps to the legacy 6 for the old column."""
    return ARCHETYPE_BY_OPENING.get(dna.get("opening_device", ""), "other")


def legacy_archetype(dna: dict) -> str:
    return LEGACY_ARCHETYPES.get(archetype(dna), "other")