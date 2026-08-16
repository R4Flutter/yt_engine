"""Regression tests for scorecard bypasses found by the adversarial break lab."""
from analyzer import score


def _settings():
    return {
        "analyzer": {
            "gate": {
                "payoff_promise_sec": 8,
                "min_wpm": 145,
                "cuts_per_min_min": 10,
                "cuts_per_min_max": 24,
                "max_static_shot_sec": 8,
                "loudness_lufs_min": -15,
                "loudness_lufs_max": -13,
            },
            "pass": {"overall_min": 80, "hook_min": 75, "retention_min": 70, "packaging_min": 75},
        }
    }


def _media():
    return {
        "duration_sec": 45,
        "width": 1080,
        "height": 1920,
        "scenes": {"cuts_per_min": 0, "longest_static_shot": 45},
        "loudness": {},
    }


def test_assume_voice_can_never_pass(monkeypatch, tmp_path):
    video = tmp_path / "black.mp4"
    video.write_bytes(b"fixture")
    monkeypatch.setattr(score, "load_settings", _settings)
    monkeypatch.setattr(score, "load_benchmarks", lambda: None)
    monkeypatch.setattr(score, "media_analyze", lambda _: _media())
    result = score.score_video(str(video), "A specific 10 dollar story", assume_voice=True)
    assert result["verdict"] == "FIX_REQUIRED"
    assert result["score"] < 80
    assert not result["verification"]["complete"]
    assert any(c["id"] == "HOOK_ASSUMED" and not c["ok"] for c in result["checks"])


def test_unmeasured_categories_never_disappear_from_denominator(monkeypatch, tmp_path):
    video = tmp_path / "black.mp4"
    video.write_bytes(b"fixture")
    monkeypatch.setattr(score, "load_settings", _settings)
    monkeypatch.setattr(score, "load_benchmarks", lambda: None)
    monkeypatch.setattr(score, "media_analyze", lambda _: _media())
    monkeypatch.setattr(score, "transcribe", lambda *_: {"hook_promise_sec": 1, "wpm": 180})
    result = score.score_video(str(video), "A specific 10 dollar story")
    assert result["category_scores"]["Thumbnail"] == 0
    assert result["category_scores"]["Topic momentum"] == 0
    assert result["verdict"] == "FIX_REQUIRED"
    assert not result["gates"]["all_required_categories_verified"]


def test_multiple_checks_cannot_inflate_a_category_over_100(monkeypatch, tmp_path):
    video = tmp_path / "ok.mp4"
    video.write_bytes(b"fixture")
    monkeypatch.setattr(score, "load_settings", _settings)
    monkeypatch.setattr(score, "load_benchmarks", lambda: None)
    monkeypatch.setattr(score, "media_analyze", lambda _: {
        "duration_sec": 30, "width": 1080, "height": 1920,
        "scenes": {"cuts_per_min": 15, "longest_static_shot": 2},
        "loudness": {"integrated_lufs": -14},
    })
    monkeypatch.setattr(score, "transcribe", lambda *_: {"hook_promise_sec": 2, "wpm": 180})
    result = score.score_video(str(video), "A specific 10 dollar story")
    assert all(0 <= value <= 100 for value in result["category_scores"].values())
    assert result["category_scores"]["Retention engineering"] == 100
