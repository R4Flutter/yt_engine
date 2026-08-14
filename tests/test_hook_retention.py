"""Tests for miner.hook_retention — within-video normalized retention metrics.

Covers: normalization, fixed marks, shape metrics, degraded inputs.
"""
import json

import numpy as np
import pytest

from miner.hook_retention import RETENTION_MARKS, retention_metrics


def _curve(n=200, seed=0):
    rng = np.random.default_rng(seed)
    base = np.linspace(0.6, 0.2, n)
    return base + 0.15 * rng.standard_normal(n)


def _points_json(curve):
    """yt-dlp heatmap format: value per segment (start_time..end_time)."""
    pts = []
    for i, v in enumerate(curve):
        pts.append({"start_time": i, "end_time": i + 1, "value": float(v)})
    return json.dumps(pts)


def test_normalized_metrics_present():
    m = retention_metrics(_points_json(_curve()), 300.0)
    assert m is not None
    for mark in RETENTION_MARKS:
        assert f"retention_{mark}s" in m
    assert "early_retention" in m
    assert "retention_slope" in m
    assert "retention_drop" in m
    assert "retention_recovery" in m
    assert "peak_retention" in m
    assert "volatility" in m


def test_z_scores_are_within_video():
    m = retention_metrics(_points_json(_curve()), 300.0)
    # z-scored against the video's own mean/std -> values are centered
    vals = [m[f"retention_{k}s"] for k in RETENTION_MARKS]
    assert all(abs(v) <= 4 for v in vals)


def test_strong_rising_hook_scores_well():
    # starts below the video mean then spikes -> positive slope, positive z
    rng = np.random.default_rng(7)
    n = 200
    x = np.linspace(0, 1, n)
    curve = 0.5 + 0.8 * x + 0.1 * rng.standard_normal(n)
    m = retention_metrics(_points_json(curve), 300.0)
    assert m["retention_slope"] > 0


def test_flat_curve_low_volatility():
    curve = np.full(200, 0.5) + 0.01 * np.random.default_rng(1).standard_normal(200)
    m = retention_metrics(_points_json(curve), 300.0)
    assert m["volatility"] < 0.3


def test_peak_detection():
    n = 200
    curve = np.linspace(0.5, 0.3, n)
    curve[25] = 0.99  # single big rewatch spike at t=25 (inside the hook window)
    m = retention_metrics(_points_json(curve), 300.0)
    assert m["peak_sec"] == pytest.approx(25.0, abs=1.5)
    assert m["peak_retention"] > 3  # z >> 0


def test_retention_marks_dont_exceed_curve_len():
    m = retention_metrics(_points_json(_curve(n=50)), 300.0)
    assert m is not None
    # 30s mark exists even for short curves (min(index, n-1))
    assert "retention_30s" in m


@pytest.mark.parametrize("bad", [
    "not json",
    "",
    "[]",
    '{"x": 1}',
])
def test_bad_heatmaps_return_none(bad):
    assert retention_metrics(bad, 300.0) is None


def test_empty_points():
    assert retention_metrics("[]", 300.0) is None


def test_dict_input_accepted():
    pts = [{"start_time": i, "end_time": i + 1, "value": float(v)}
           for i, v in enumerate(_curve(n=100))]
    m = retention_metrics(pts, 300.0)
    assert m is not None