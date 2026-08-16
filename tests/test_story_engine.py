from miner.story_engine import build_blueprint, rank_hooks


def test_contradiction_hook_ranks_high():
    hooks = rank_hooks(
        [
            "This company is successful.",
            "This company made billions, but the customers barely use it. Why does that work?",
        ],
        ["The company made billions.", "Customers barely use it."],
    )
    assert hooks[0].score > hooks[1].score
    assert "contradiction" in hooks[0].reasons
    assert "unanswered question/open loop" in hooks[0].reasons


def test_blueprint_has_longform_arc():
    bp = build_blueprint(
        "A subscription business",
        "Unused subscriptions can still be economically valuable.",
        ["20.8 million members"],
        ["An empty room can be more valuable than a full one. Why?"]
    )
    stages = [x["stage"] for x in bp.narrative_arc]
    assert stages[0] == "cold_open"
    assert "reversal" in stages
    assert stages[-1] == "hard_stop"
    assert len(bp.hook_candidates) == 1
