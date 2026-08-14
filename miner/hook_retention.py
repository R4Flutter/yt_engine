"""M3 Hook retention — heatmap intelligence for the opening (Phase 3).

The most important layer. Aligns the word-timestamped hook beats to the
YouTube "Most Replayed" curve and derives hook-level retention metrics.

Scientific rules enforced here:
  * heat is z-scored WITHIN each video — raw heat mostly reflects how popular
    the video is, so comparing raw values across videos is meaningless
  * position is controlled: the within-video z is computed against the same
    video's own mean/std, and absolute hook-window heat is also reported
    relative to the video's own peak
  * beat-level and video-level metrics are kept separate so downstream
    pattern mining can group by video (sentences within a video are not
    independent samples)
"""

from __future__ import annotations

import json

import numpy as np

from miner.alignment import resample_curve

RETENTION_MARKS = (1, 3, 5, 10, 15, 20, 30)  # seconds into the video


def retention_metrics(points_json: str, duration: float,
                      hook_start: float = 0.0, hook_end: float = 30.0) -> dict | None:
    """Full hook-window retention profile from a heatmap.

    Returns within-video z-scores at 1..30 s plus derived shape metrics, or
    None when the heatmap is too thin to trust.
    """
    try:
        points = json.loads(points_json) if isinstance(points_json, str) else points_json
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(points, list) or not all(
            isinstance(p, dict) for p in points):
        return None
    curve = resample_curve(points, duration)
    if curve is None or len(curve) < 40:
        return None

    n = len(curve)
    mu, sd = float(curve.mean()), float(curve.std()) or 1e-6
    z = (curve - mu) / sd

    window = slice(int(hook_start), min(int(hook_end), n))
    win = z[window]
    if len(win) < 3:
        return None

    out = {}
    # retention at fixed marks (z within the video)
    for m in RETENTION_MARKS:
        i = min(m, n - 1)
        out[f"retention_{m}s"] = round(float(z[i]), 3)

    # early retention: mean z over the first 5 seconds
    out["early_retention"] = round(float(z[1:min(6, n)].mean()), 3)

    # retention slope: linear fit over the hook window (z/sec)
    if len(win) >= 3:
        x = np.arange(len(win), dtype=float)
        slope = np.polyfit(x, win, 1)[0]
        out["retention_slope"] = round(float(slope), 4)
    else:
        out["retention_slope"] = None

    # drop: largest fall from a running peak within the window
    peak = -np.inf
    max_drop = 0.0
    peak_at = 0
    for i, v in enumerate(win):
        if v > peak:
            peak = v
            peak_at = i
        if peak - v > max_drop:
            max_drop = peak - v
    out["retention_drop"] = round(float(max_drop), 3)

    # recovery: z at 30s minus z at 10s (did the hook pay off?)
    i10, i30 = min(10, n - 1), min(30, n - 1)
    out["retention_recovery"] = round(float(z[i30] - z[i10]), 3)

    # peak: strongest rewatch moment inside the hook window (absolute position)
    out["peak_retention"] = round(float(win.max()), 3)
    out["peak_sec"] = round(float(peak_at + hook_start), 1)

    # volatility: pacing/instability — raw-window coefficient of variation.
    # (z-std would be ~1 for every curve since z is standardized; raw CV
    # actually distinguishes a calm curve from a choppy one)
    raw_win = curve[window]
    out["volatility"] = round(float(raw_win.std() / mu), 3)

    return out


def hook_level_from_db(conn, video_id: str, hook_start: float = 0.0,
                       hook_end: float = 30.0) -> dict | None:
    """Convenience: pull heatmap + duration for one video and score its hook."""
    row = conn.execute(
        "SELECT h.points_json, v.duration_sec FROM heatmaps h "
        "JOIN videos v ON v.video_id = h.video_id WHERE h.video_id = ?",
        (video_id,)).fetchone()
    if not row:
        return None
    return retention_metrics(row["points_json"], row["duration_sec"],
                             hook_start, hook_end)