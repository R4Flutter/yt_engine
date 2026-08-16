from miner.script_writer import build_brief, build_retention_map, target_words, validate_script


def test_target_words_is_long_form_scale():
    assert 1500 < target_words(20) < 3500


def test_retention_map_is_documentary_not_shorts():
    points = build_retention_map(20)
    assert points[0]["device"] == "cold_open"
    assert any(x["device"] == "reversal" for x in points)
    assert points[-1]["device"] == "hard_stop"
    assert len(points) == 9


def test_brief_has_three_layer_hook_contract():
    brief = build_brief("Why a subscription business works", [], 20)
    layers = brief.hook_contract["cold_open_layers"]
    assert len(layers) == 3
    assert "evidence" in layers[1]
    assert "hook claim" in layers[2]


def test_validation_rejects_missing_machine_contract():
    result = validate_script("too short", [], 20)
    assert not result.passed
    assert result.errors


def test_validation_flags_unverified_numbers():
    text = """[VISUAL INTENT: empty room]\nNARRATION\nThe company made $999 billion.\n[RETENTION DEVICE: contradiction]\n""" + "x" * 1200
    result = validate_script(text, ["The company made $10 million"], 20)
    assert any("999" in warning for warning in result.warnings)
