"""Tests for miner.hook_dna — Hook DNA extraction.

Covers: opening devices, curiosity mechanisms, emotions, stakes, promises,
specificity, narrative structure, open loop, archetype mapping, edge cases.
"""
import pytest

from miner.hook_dna import (ARCHETYPE_BY_OPENING, CURIOSITY, EMOTIONS,
                            PROMISES, STAKES, archetype, extract_dna,
                            legacy_archetype)

FIXTURES = [
    ("This company was worth 40 billion dollars. Then everything collapsed.",
     "shocking_fact", "money", "bold_claim"),
    ("Why does Planet Fitness keep charging you every month?",
     "direct_question", "none", "question"),
    ("Everyone thinks Netflix is profitable. It is not.",
     "contrarian_claim", "money", "bold_claim"),
    ("In 2013, Adobe raised the price of Photoshop. Nobody noticed why.",
     "story_medias_res", "money", "story"),
    ("I spent 3 years building a startup that lost everything.",
     "confession", "time", "cold_open_stakes"),
    ("Never trust a subscription you cannot cancel.",
     "negative_opening", "reputation", "negative"),
]


@pytest.mark.parametrize("text,opening,stakes,arch", FIXTURES)
def test_extract_dna_basics(text, opening, stakes, arch):
    d = extract_dna(text)
    assert d["opening_device"] == opening
    assert d["stakes_type"] == stakes
    assert archetype(d) == arch


def test_number_specificity():
    d = extract_dna("It cost $10,427 to fix. That is real money.")
    assert d["specific_number_count"] >= 1
    assert d["has_dollar"] == 1
    d2 = extract_dna("It cost $10,000. Round estimate.")
    assert d2["specific_number_count"] == 0  # round numbers are not specific


def test_question_detection():
    d = extract_dna("Why would anyone pay for this?")
    assert d["has_question"] == 1
    assert d["open_loop"] == 1
    assert d["curiosity_mechanism"] == "unanswered_why"


def test_open_loop_absent_in_flat_statement():
    d = extract_dna("Planet Fitness charges ten dollars a month for membership.")
    assert d["open_loop"] == 0
    assert d["curiosity_mechanism"] == "none"


def test_narrative_structure_order():
    d = extract_dna("This company was worth $40 billion. Then it collapsed.")
    assert "STATE" in d["narrative_structure"]
    assert d["narrative_structure"].index("STATE") < \
        d["narrative_structure"].index("REVERSAL")


def test_promise_detection():
    d = extract_dna("Let me show you how the subscription works.")
    assert d["promise_type"] == "explanation"


def test_entity_detection():
    d = extract_dna("Adobe raised the price and Netflix followed the same playbook.")
    assert "Adobe" in d["entities"] or "Netflix" in d["entities"]


def test_emotions_present():
    d = extract_dna("It was a terrifying scam that stole everything from investors.")
    assert "fear" in d["emotions"] or "anger" in d["emotions"]


def test_legacy_archetype_mapping():
    d = extract_dna("This company was worth 40 billion dollars. Then it collapsed.")
    assert legacy_archetype(d) in {"bold_claim", "question", "story",
                                   "cold_open_stakes", "stat", "other"}


def test_short_hook():
    d = extract_dna("Why?")
    assert d["word_count"] == 1
    assert d["has_question"] == 1


def test_empty_hook():
    assert extract_dna("") == {}
    assert extract_dna("   ") == {}


def test_long_hook_no_crash():
    d = extract_dna("The company " * 300 + "collapsed finally.")
    assert d["word_count"] > 100


def test_lexicons_nonempty():
    assert len(ARCHETYPE_BY_OPENING) >= 15
    assert len(CURIOSITY) >= 10
    assert len(EMOTIONS) >= 10
    assert len(STAKES) >= 8
    assert len(PROMISES) >= 6