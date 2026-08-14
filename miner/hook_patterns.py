"""M3 Hook pattern discovery (Phase 4) — measure what actually works.

For every Hook DNA feature compute, against within-video-normalized hook
retention:

    sample size (videos, not hooks)
    mean/median effect (z-units, Cohen's d for binary features)
    bootstrap 95% CI over videos  (sentences within a video are correlated —
                                   resample videos, never hooks)
    channel consistency          (sign held in how many channels)
    video consistency            (sign held in how many videos)
    confidence label             (HIGH/MEDIUM/LOW/INSUFFICIENT DATA)

Output: reports/hook_patterns.json + printed table.
"""

from __future__ import annotations

import json

import numpy as np
from config import ROOT, resolve_path


def _confidence(n_videos: int, ci_excludes_zero: bool) -> str:
    if n_videos < 5:
        return "INSUFFICIENT DATA"
    if n_videos < 15:
        return "LOW" if not ci_excludes_zero else "MEDIUM"
    return "MEDIUM" if not ci_excludes_zero else "HIGH"


def discover(conn, settings) -> dict:
    rows = conn.execute(
        """SELECT l.video_id, v.channel_id, l.opening_device, l.curiosity_mechanism,
                  l.emotional_mechanism, l.stakes_type, l.promise_type,
                  l.first_number_sec, l.first_entity_sec, l.promise_sec,
                  l.word_count, l.retention_10s, l.early_retention,
                  l.retention_slope, l.retention_30s,
                  COALESCE(vf.hook_dna_json, '{}') AS dna_json
           FROM hook_library l JOIN videos v ON v.video_id = l.video_id
           LEFT JOIN video_features vf ON vf.video_id = l.video_id
           WHERE l.retention_10s IS NOT NULL""").fetchall()
    if not rows:
        return {"n_videos": 0, "findings": []}

    def _dna(r) -> dict:
        try:
            return json.loads(r["dna_json"] or "{}")
        except json.JSONDecodeError:
            return {}

    rows = [dict(r) for r in rows]
    for r in rows:
        d = _dna(r)
        r["has_question"] = int(d.get("has_question", 0))
        r["open_loop"] = int(d.get("open_loop", 0))

    # group by video so bootstrap resamples videos, not hooks
    by_video: dict[str, list[dict]] = {}
    for r in rows:
        by_video.setdefault(r["video_id"], []).append(dict(r))
    by_channel: dict[str, set[str]] = {}
    for r in rows:
        by_channel.setdefault(r["channel_id"], set()).add(r["video_id"])

    videos = list(by_video.keys())
    rng = np.random.default_rng(7)

    def _video_effect(feature_getter, binary: bool) -> dict:
        """Feature -> per-video mean effect on retention_10s (z-units).

        One sample PER VIDEO (mean the feature and label within video), so
        the bootstrap resamples videos — never hooks.
        """
        fv, lv = [], []
        for vid in videos:
            group = by_video[vid]
            fv.append(float(np.mean([feature_getter(g) for g in group])))
            lv.append(float(np.mean([g["retention_10s"] for g in group])))
        fv, lv = np.array(fv), np.array(lv)

        present = fv > 0 if binary else fv > fv.mean()
        absent = ~present
        if present.sum() < 2 or absent.sum() < 2:
            return None
        effect = lv[present].mean() - lv[absent].mean()

        # bootstrap over videos
        boot = []
        for _ in range(400):
            idx = rng.choice(len(videos), size=len(videos), replace=True)
            p = fv[idx] > 0 if binary else fv[idx] > fv.mean()
            a = ~p
            if p.sum() < 2 or a.sum() < 2:
                boot.append(0.0)
                continue
            boot.append(lv[idx][p].mean() - lv[idx][a].mean())
        lo, hi = np.percentile(boot, [2.5, 97.5])

        # channel consistency: in how many channels does the SAME sign hold?
        # (only channels with >=2 samples count toward the denominator)
        ch_eff, ch_tot = 0, 0
        for ch, vids_ch in by_channel.items():
            if len(vids_ch) < 2:
                continue
            ch_tot += 1
            ch_p = [lv[i] for i, vid in enumerate(videos)
                    if vid in vids_ch and present[i]]
            ch_a = [lv[i] for i, vid in enumerate(videos)
                    if vid in vids_ch and absent[i]]
            if ch_p and ch_a and np.mean(ch_p) > np.mean(ch_a):
                ch_eff += 1

        return {
            "sample_size_videos": int(present.sum()),
            "effect_z": round(float(effect), 3),
            "ci95": [round(float(lo), 3), round(float(hi), 3)],
            "robust": bool(lo > 0 or hi < 0),
            "channel_consistency": f"{ch_eff}/{ch_tot}",
            "confidence": _confidence(len(videos), bool(lo > 0 or hi < 0)),
        }

    findings = []
    binary_features = [
        ("opening_shock", lambda g: g["opening_device"] in ("shocking_fact", "impossible_outcome")),
        ("opening_question", lambda g: g["opening_device"] == "direct_question"),
        ("opening_story", lambda g: g["opening_device"] == "story_medias_res"),
        ("curiosity_gap_present", lambda g: g["curiosity_mechanism"] in ("information_gap", "unanswered_why", "mystery")),
        ("question_present", lambda g: g["has_question"]),
        ("open_loop", lambda g: g["open_loop"]),
        ("stakes_money", lambda g: g["stakes_type"] == "money"),
        ("promise_present", lambda g: g["promise_type"] not in ("none",)),
    ]
    for name, getter in binary_features:
        r = _video_effect(getter, binary=True)
        if r:
            findings.append({"feature": name, **r})

    # numeric features: first-number/promise timing correlation.
    # Videos WITHOUT the feature are excluded from that feature's analysis —
    # never imputed with 99 (which would conflate "absent" with "late").
    numeric_features = [
        ("first_number_sec", lambda g: g["first_number_sec"]),
        ("first_entity_sec", lambda g: g["first_entity_sec"]),
        ("promise_sec", lambda g: g["promise_sec"]),
        ("word_count", lambda g: g["word_count"]),
    ]
    for name, getter in numeric_features:
        pairs = []
        for vid in videos:
            group = by_video[vid]
            vals = [getter(g) for g in group if getter(g) is not None]
            if not vals:
                continue
            lv = float(np.mean([g["retention_10s"] for g in group]))
            pairs.append((float(np.mean(vals)), lv))
        if len(pairs) < 5:
            continue
        fv, lv = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        corr = float(np.corrcoef(fv, lv)[0, 1]) if fv.std() > 0 else 0.0
        findings.append({
            "feature": name, "correlation_z_per_unit": round(corr, 3),
            "sample_size_videos": len(pairs),
            "confidence": _confidence(len(pairs), abs(corr) > 0.25),
        })

    return {
        "n_videos": len(videos),
        "n_hooks": len(rows),
        "findings": findings,
    }


def main() -> int:
    from config import fix_console, load_settings
    from db import get_connection, init_db
    fix_console()
    conn = get_connection()
    init_db(conn)
    settings = load_settings()
    res = discover(conn, settings)
    print(f"HOOK PATTERNS  (n={res['n_videos']} videos, {res['n_hooks']} hooks)")
    print(f"{'feature':<24} {'effect':>8} {'95% CI':>18} {'consistency':>12}  confidence")
    print("-" * 80)
    for f in res["findings"]:
        if "effect_z" in f:
            mark = "*" if f.get("robust") else " "
            ci = f"[{f['ci95'][0]:+.3f},{f['ci95'][1]:+.3f}]"
            print(f"{f['feature']:<24} {f['effect_z']:+8.3f}{mark} {ci:>18} "
                  f"{f['channel_consistency']:>12}  {f['confidence']}")
        else:
            print(f"{f['feature']:<24} {f['correlation_z_per_unit']:+8.3f} "
                  f"{'':>18} {'':>12}  {f['confidence']}")
    print("\n* = 95% bootstrap CI (over videos) excludes zero")
    out = resolve_path(load_settings()["paths"]["reports"]) / "hook_patterns.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())