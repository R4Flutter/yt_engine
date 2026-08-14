"""M3 Miner — YouTube hook intelligence + generation engine.

One CLI, composable commands, backwards compatible (no args = old `mine`):

    python -m miner.hooks mine                      # Hook DNA for all transcripts
    python -m miner.hooks analyze                   # retention intelligence (heatmap)
    python -m miner.hooks build-library             # join DNA+timing+retention -> hook_library
    python -m miner.hooks patterns              # what actually works (effect sizes)
    python -m miner.hooks patterns-learned      # LEARNED pattern library (interactions)
    python -m miner.hooks train --build         # training set + per-horizon models
    python -m miner.hooks predict "Why Netflix raised prices"   # learned predictions
    python -m miner.hooks benchmark-model       # training benchmark: RAM + time
    python -m miner.hooks generate "Why Netflix raised prices" --mode retention --duration 8
    python -m miner.hooks explain 12                # why does library hook #12 work?
    python -m miner.hooks mutate "Your hook text" --style shocking
    python -m miner.hooks benchmark                 # corpus + pipeline status
    python -m miner.hooks record-outcome 1 --my-video 3   # feedback loop
    python -m miner.hooks --export                  # legacy JSON export (kept)

The system never guarantees virality: everything downstream of measurement
is labeled OBSERVED / INFERRED / PREDICTED with confidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import fix_console, load_settings, resolve_path
from db import get_connection, init_db
from miner.hook_dna import archetype, extract_dna, legacy_archetype
from miner.hook_gen import LENGTH_TARGETS, MODES, generate, mutate
from miner.hook_retention import retention_metrics


# ------------------------------------------------------------------- mine

def mine(conn, settings) -> int:
    """Hook DNA extraction for every transcript hook (LEVELS 1-4)."""
    rows = conn.execute(
        """SELECT t.video_id, t.hook_text
           FROM transcripts t JOIN videos v ON v.video_id = t.video_id
           WHERE t.hook_text IS NOT NULL AND length(t.hook_text) > 10"""
    ).fetchall()
    n = 0
    for r in rows:
        dna = extract_dna(r["hook_text"])
        arch = archetype(dna)
        leg = legacy_archetype(dna)
        conn.execute(
            """UPDATE video_features SET hook_archetype=?, hook_dna_json=? WHERE video_id=?""",
            (leg, json.dumps(dna, ensure_ascii=False), r["video_id"]))
        n += 1
    conn.commit()
    print(f"[mine] Hook DNA written for {n} hooks")
    return n


# --------------------------------------------------------------- analyze

def analyze(conn, settings) -> int:
    """Retention intelligence: hook-window metrics from heatmaps (LEVEL 6)."""
    rows = conn.execute(
        """SELECT v.video_id, h.points_json, v.duration_sec
           FROM heatmaps h JOIN videos v ON v.video_id = h.video_id
           WHERE v.duration_sec >= ?""",
        (settings["align"]["min_duration_sec"],)).fetchall()
    n = 0
    for r in rows:
        m = retention_metrics(r["points_json"], r["duration_sec"])
        if not m:
            continue
        conn.execute(
            """INSERT INTO hook_library (video_id, retention_1s, retention_3s,
                 retention_5s, retention_10s, retention_15s, retention_20s,
                 retention_30s, early_retention, retention_slope, retention_drop,
                 retention_recovery, peak_retention, peak_sec, volatility)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(video_id) DO UPDATE SET
                 retention_1s=excluded.retention_1s, retention_3s=excluded.retention_3s,
                 retention_5s=excluded.retention_5s, retention_10s=excluded.retention_10s,
                 retention_15s=excluded.retention_15s, retention_20s=excluded.retention_20s,
                 retention_30s=excluded.retention_30s, early_retention=excluded.early_retention,
                 retention_slope=excluded.retention_slope, retention_drop=excluded.retention_drop,
                 retention_recovery=excluded.retention_recovery, peak_retention=excluded.peak_retention,
                 peak_sec=excluded.peak_sec, volatility=excluded.volatility""",
            (r["video_id"], *[m[f"retention_{s}s"] for s in (1, 3, 5, 10, 15, 20, 30)],
             m["early_retention"], m["retention_slope"], m["retention_drop"],
             m["retention_recovery"], m["peak_retention"], m["peak_sec"],
             m["volatility"]))
        n += 1
    conn.commit()
    print(f"[analyze] retention profile for {n} videos")
    return n


# ---------------------------------------------------------- build-library

def build_library(conn, settings) -> int:
    """Assemble the structured hook library: DNA + timing + retention joined.

    One row per video (the hook = its first-30s opening). Prioritized by
    outlier score downstream — every video is kept, ranked by evidence.
    """
    from miner.hook_beats import analyze_opening
    rows = conn.execute(
        """SELECT t.video_id, t.hook_text, t.words_json, v.title, v.outlier_score,
                  v.duration_sec, c.title AS channel, c.niche_tag
           FROM transcripts t
           JOIN videos v ON v.video_id = t.video_id
           LEFT JOIN channels c ON c.channel_id = v.channel_id
           WHERE t.hook_text IS NOT NULL AND length(t.hook_text) > 10"""
    ).fetchall()
    n = 0
    for r in rows:
        dna = extract_dna(r["hook_text"])
        beats = {}
        if r["words_json"]:
            try:
                words = json.loads(r["words_json"])
            except (json.JSONDecodeError, TypeError):
                words = None
            if words:
                beats = analyze_opening(words, float(r["duration_sec"] or 0))
        hook_text = r["hook_text"]
        # keep legacy column in sync
        conn.execute(
            """UPDATE video_features SET hook_archetype=?, hook_dna_json=?
               WHERE video_id=?""",
            (legacy_archetype(dna), json.dumps(dna, ensure_ascii=False),
             r["video_id"]))
        # upsert the library row
        conn.execute(
            """INSERT INTO hook_library (video_id, title, channel, niche_tag,
                 outlier_score, hook_text, hook_start, hook_end, word_count,
                 duration, wpm, archetype, opening_device, curiosity_mechanism,
                 emotional_mechanism, stakes_type, promise_type, narrative_structure,
                 first_number_sec, first_entity_sec, first_stakes_sec,
                 first_curiosity_sec, promise_sec, analyzed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(video_id) DO UPDATE SET
                 title=excluded.title, channel=excluded.channel,
                 niche_tag=excluded.niche_tag, outlier_score=excluded.outlier_score,
                 hook_text=excluded.hook_text, hook_start=excluded.hook_start,
                 hook_end=excluded.hook_end, word_count=excluded.word_count,
                 duration=excluded.duration, wpm=excluded.wpm,
                 archetype=excluded.archetype, opening_device=excluded.opening_device,
                 curiosity_mechanism=excluded.curiosity_mechanism,
                 emotional_mechanism=excluded.emotional_mechanism,
                 stakes_type=excluded.stakes_type, promise_type=excluded.promise_type,
                 narrative_structure=excluded.narrative_structure,
                 first_number_sec=excluded.first_number_sec,
                 first_entity_sec=excluded.first_entity_sec,
                 first_stakes_sec=excluded.first_stakes_sec,
                 first_curiosity_sec=excluded.first_curiosity_sec,
                 promise_sec=excluded.promise_sec, analyzed_at=excluded.analyzed_at""",
            (r["video_id"], r["title"], r["channel"], r["niche_tag"],
             r["outlier_score"], hook_text,
             beats.get("hook_start"), beats.get("hook_end"),
             beats.get("word_count") or dna["word_count"],
             beats.get("duration"), beats.get("wpm"),
             archetype(dna), dna["opening_device"], dna["curiosity_mechanism"],
             dna["emotional_mechanism"], dna["stakes_type"], dna["promise_type"],
             dna["narrative_structure"],
             beats.get("first_number_sec"), beats.get("first_entity_sec"),
             beats.get("first_stakes_sec"), beats.get("first_curiosity_sec"),
             beats.get("promise_sec"), _now()))
        n += 1
    conn.commit()

    # embed everything for retrieval (deterministic TF-IDF, stored as BLOB)
    _embed_all(conn)
    print(f"[build-library] {n} hooks in library")
    return n


def _now() -> str:
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _embed_all(conn) -> None:
    from miner.hook_retrieval import build_embedder, embed
    rows = conn.execute(
        "SELECT id, hook_text FROM hook_library WHERE hook_text IS NOT NULL").fetchall()
    if not rows:
        return
    vec = build_embedder([r["hook_text"] for r in rows])
    for r in rows:
        conn.execute("UPDATE hook_library SET embedding=? WHERE id=?",
                     (embed(vec, r["hook_text"]), r["id"]))
    conn.commit()
    print(f"[build-library] embedded {len(rows)} hooks")


# ---------------------------------------------------------------- explain

def explain(conn, hook_id: int) -> None:
    row = conn.execute(
        """SELECT l.*, v.title AS video_title FROM hook_library l
           LEFT JOIN videos v ON v.video_id = l.video_id WHERE l.id = ?""",
        (hook_id,)).fetchone()
    if not row or not row["hook_text"]:
        print(f"[explain] no analyzable hook with id={hook_id} "
              f"(row exists but has no hook text — retention-only row)")
        return
    from miner.hook_dna import extract_dna
    from miner.hook_gen import _why_it_works, _risks, tag_factuality
    dna = extract_dna(row["hook_text"])
    fact = tag_factuality(row["hook_text"], [], dna.get("entities") or [])
    print(f"\nHOOK #{row['id']}  —  {row['hook_text'][:200]}")
    print(f"Score: n/a · outlier {row['outlier_score']:.1f}x · retention@10s {row['retention_10s']}")
    print("\nDNA:")
    print(f"  archetype          {row['archetype']}")
    print(f"  opening device     {row['opening_device']}")
    print(f"  curiosity          {row['curiosity_mechanism']}")
    print(f"  emotion            {row['emotional_mechanism']}")
    print(f"  stakes             {row['stakes_type']}")
    print(f"  promise            {row['promise_type']}")
    print(f"  structure          {row['narrative_structure']}")
    if row["first_number_sec"] is not None:
        print(f"  first number at    {row['first_number_sec']}s · first stakes {row['first_stakes_sec']}s · promise {row['promise_sec']}s")
    print("\nWHY IT WORKS:")
    for w in _why_it_works(dna):
        print(f"  ✓ {w}")
    print("\nRISKS:")
    for w in _risks(fact, dna):
        print(f"  ⚠ {w}")
    print(f"\nEVIDENCE: from video '{row['video_title']}' (channel {row['channel']}, niche {row['niche_tag']})")
    print(f"CONFIDENCE: per-video measurement — treat as OBSERVED for this video only")


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("mine", help="Hook DNA extraction (LEVELS 1-4)")
    sub.add_parser("analyze", help="hook-window retention intelligence (LEVEL 6)")
    sub.add_parser("build-library", help="assemble hook_library (DNA+timing+retention)")
    sub.add_parser("patterns", help="effect sizes: what actually works")
    sub.add_parser("patterns-learned", help="LEARNED pattern library (incl. interactions)")
    sub.add_parser("benchmark-model", help="training benchmark: RAM + time + rows/sec")

    t = sub.add_parser("train", help="build training set + train per-horizon models")
    t.add_argument("--build", action="store_true", help="(re)build hook_training_examples first")
    t.add_argument("--replace", action="store_true", help="wipe + rebuild the training table")

    p = sub.add_parser("predict", help="learned prediction with explanations for a hook")
    p.add_argument("topic", nargs="*", help="topic, or --text for a raw hook")
    p.add_argument("--text", default=None, help="predict a raw hook text instead of generating")
    p.add_argument("--json", action="store_true", help="emit structured JSON")
    sub.add_parser("benchmark", help="corpus + pipeline status")

    g = sub.add_parser("generate", help="multi-stage hook generation")
    g.add_argument("topic", nargs="*", help="video topic, e.g. \"Why Lamborghini makes so much money\"")
    g.add_argument("--mode", choices=sorted(MODES), default="retention_optimized")
    g.add_argument("--duration", type=int, default=8, choices=sorted(LENGTH_TARGETS))
    g.add_argument("--facts", nargs="*", default=[], help="verified facts, e.g. \"made $2.3B in 2024\"")
    g.add_argument("--niche", default=None, help="niche tag to boost (e.g. story_doc)")
    g.add_argument("--llm", action="store_true", help="enable optional LLM critique pass")
    g.add_argument("--json", action="store_true", help="emit structured JSON")

    e = sub.add_parser("explain", help="why does a library hook work?")
    e.add_argument("hook_id", type=int)

    m = sub.add_parser("mutate", help="transform a hook")
    m.add_argument("text", nargs="*")
    m.add_argument("--style", default="shocking",
                   choices=sorted({"more_" + s for s in
                                   ("shocking", "curious", "confrontational", "cinematic",
                                    "natural", "documentary", "story", "contrarian",
                                    "money", "investigative")} | {"shorter", "faster",
                                   "more_usa_audience_native"}))

    r = sub.add_parser("record-outcome", help="feedback loop: hook -> published video performance")
    r.add_argument("generation_id", type=int)
    r.add_argument("--my-video", type=int, required=True)

    ap.add_argument("--export", action="store_true", help="legacy JSON export of the library")
    args = ap.parse_args(argv)

    settings = load_settings()
    conn = get_connection()
    init_db(conn)

    # backwards compatibility: bare `python -m miner.hooks` == mine
    if args.cmd is None and not args.export:
        args.cmd = "mine"

    if args.cmd == "mine":
        mine(conn, settings)
    elif args.cmd == "analyze":
        analyze(conn, settings)
    elif args.cmd == "build-library":
        build_library(conn, settings)
    elif args.cmd == "patterns":
        from miner.hook_patterns import main as _p
        return _p()
    elif args.cmd == "patterns-learned":
        from miner.hook_learn import discover_patterns
        res = discover_patterns(conn, settings)
        print(f"LEARNED PATTERNS  (scope {res['scope']}, n={res['n_videos']} videos, "
              f"{res['n_hooks']} hooks)")
        print(f"{'pattern':<38} {'effect':>8} {'95% CI':>18} {'ch':>5}  confidence")
        print("-" * 88)
        for p in res["patterns"]:
            mark = "*" if p["robust"] else " "
            ci = f"[{p['ci95'][0]:+.3f},{p['ci95'][1]:+.3f}]"
            print(f"{p['pattern_key']:<38} {p['effect_z']:+8.3f}{mark} {ci:>18} "
                  f"{p['channel_consistency']:>5}  {p['confidence']}  "
                  f"({p['kind']}, best@{p['best_duration_sec']}s)")
        print("\n* = 95% bootstrap CI (over videos) excludes zero · LEARNED from corpus, "
              "not authored")
        return 0
    elif args.cmd == "train":
        return _train_cli(conn, settings, args)
    elif args.cmd == "predict":
        return _predict_cli(conn, settings, args)
    elif args.cmd == "benchmark-model":
        return _benchmark_model_cli(conn, settings)
    elif args.cmd == "benchmark":
        _benchmark(conn)
    elif args.cmd == "generate":
        topic = " ".join(args.topic)
        if not topic:
            print("[generate] usage: python -m miner.hooks generate \"topic\" [--mode ...]")
            return 2
        _generate_cli(conn, settings, topic, args)
    elif args.cmd == "explain":
        explain(conn, args.hook_id)
    elif args.cmd == "mutate":
        text = " ".join(args.text)
        if not text:
            print("[mutate] usage: python -m miner.hooks mutate \"text\" --style shocking")
            return 2
        print(mutate(text, args.style))
    elif args.cmd == "record-outcome":
        _record_outcome(conn, args.generation_id, args.my_video)

    if args.export:
        _export_legacy(conn, settings)
    return 0


def _generate_cli(conn, settings, topic: str, args) -> None:
    rw = settings["hooks"]["retrieval"]
    retrieval_weights = {
        "semantic": rw["semantic_weight"], "topic": rw["topic_weight"],
        "dna": rw["dna_weight"], "outlier": rw["outlier_weight"],
        "retention": rw["retention_weight"],
    }
    # settings-driven scores: mode weights are the fallback, never the
    # configured values being ignored
    scoring = settings["hooks"].get("scoring")
    from miner.hook_retrieval import retrieve
    evidence = retrieve(conn, topic, niche=args.niche, top_k=rw["top_k"],
                        weights=retrieval_weights)
    res = generate(conn, topic, mode=args.mode, duration_target=args.duration,
                   facts=args.facts, niche=args.niche,
                   use_llm=args.llm, corpus=None, evidence=evidence,
                   retrieval_weights=retrieval_weights,
                   novelty_threshold=settings["hooks"]["generation"]["novelty_threshold"],
                   candidates=settings["hooks"]["generation"]["candidates"],
                   final_count=settings["hooks"]["generation"]["final_count"],
                   weights=scoring)

    if args.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    print(f"\nTOP HOOKS  —  {topic}")
    print(f"mode: {args.mode} · target {args.duration}s · "
          f"evidence: {res['evidence_videos'] and len(res['evidence_videos'])} retrieved hooks\n")
    for h in res["hooks"]:
        ver = " ⚠ VERIFY" if h["verification_required"] else ""
        print(f"  {h['rank']:>2}. {h['text']}{ver}")
        print(f"      score {h['score']} · {h['pattern']} · "
              f"conf {h['confidence']} · {h['factuality']}")
        if h.get("variants"):
            print(f"      variants: " + " | ".join(
                f"{k}s: {v}" for k, v in h["variants"].items() if v))

    # persist for the feedback loop (full hook objects: text + score + rank,
    # so calibration can regress predicted score against actual performance)
    conn.execute(
        """INSERT INTO hook_generations (topic, mode, duration_target, hooks_json, generated_at)
           VALUES (?,?,?,?,?)""",
        (topic, args.mode, args.duration,
         json.dumps([{"rank": h["rank"], "text": h["text"],
                      "score": h["score"], "confidence": h["confidence"]}
                     for h in res["hooks"]], ensure_ascii=False),
         _now()))
    conn.commit()
    gen_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f"\n[generation] saved as generation #{gen_id} "
          f"(record outcome: python -m miner.hooks record-outcome {gen_id} --my-video N)")


def _record_outcome(conn, gen_id: int, my_video_id: int) -> None:
    mv = conn.execute("SELECT actual_ctr, actual_avd_pct, actual_views_72h FROM my_videos "
                      "WHERE id=?", (my_video_id,)).fetchone()
    if not mv:
        print(f"[record-outcome] my_videos id={my_video_id} not found")
        return
    conn.execute(
        "UPDATE hook_generations SET my_video_id=?, actual_ctr=?, actual_avd_pct=?, "
        "actual_views_72h=? WHERE id=?",
        (my_video_id, mv["actual_ctr"], mv["actual_avd_pct"],
         mv["actual_views_72h"], gen_id))
    conn.commit()
    print(f"[record-outcome] generation #{gen_id} linked to my_videos #{my_video_id} "
          f"(CTR {mv['actual_ctr']}, AVD {mv['actual_avd_pct']}%)")


def _train_cli(conn, settings, args) -> int:
    from miner.hook_learn import build_training_data, train
    if args.build or args.replace:
        n = build_training_data(conn, settings, replace=args.replace)
        print(f"[train] built {n} training examples "
              f"(total {conn.execute('SELECT COUNT(*) FROM hook_training_examples').fetchone()[0]})")
    res = train(conn, settings)
    if res.get("status") != "trained":
        print(f"[train] {res.get('message', 'nothing to do')}")
        return 1
    print(f"[train] {res['n_videos']} videos · per-horizon models (channel-grouped CV):")
    for h, r in res["results"].items():
        print(f"  {h:>2}s  kind={r['kind']:<8} cv_rmse={r['cv_rmse']} "
              f"baseline_rmse={r['baseline_rmse']} "
              f"improvement={r['cv_r2_vs_baseline']:+.1%}")
    print("  NOTE: models kept only if >=5% better than the median baseline; "
          "predictions label their confidence honestly.")
    return 0


def _predict_cli(conn, settings, args) -> int:
    from miner.hook_learn import (HORIZONS, calibrate_from_actuals,
                                  predict_dna, predict_features)
    from miner.hook_dna import extract_dna
    from miner.hook_gen import generate
    from miner.hook_retrieval import retrieve

    if args.text:
        dna = extract_dna(args.text)
        res = {f"{h}s": predict_dna(dna, h) for h in HORIZONS}
        _print_predictions(args.text, res, args.json)
        return 0

    rw = settings["hooks"]["retrieval"]
    weights = {"semantic": rw["semantic_weight"], "topic": rw["topic_weight"],
               "dna": rw["dna_weight"], "outlier": rw["outlier_weight"],
               "retention": rw["retention_weight"]}
    topic = " ".join(args.topic)
    if not topic:
        print("[predict] usage: python -m miner.hooks predict \"topic\" | --text \"hook\"")
        return 2
    evidence = retrieve(conn, topic, top_k=rw["top_k"], weights=weights)
    out = generate(conn, topic, evidence=evidence, corpus=None,
                   retrieval_weights=weights,
                   novelty_threshold=settings["hooks"]["generation"]["novelty_threshold"],
                   candidates=settings["hooks"]["generation"]["candidates"],
                   final_count=settings["hooks"]["generation"]["final_count"])
    for hook in out["hooks"][:5]:
        dna = extract_dna(hook["text"])
        res = {f"{hh}s": predict_dna(dna, hh) for hh in HORIZONS}
        if args.json:
            print(json.dumps({"hook": hook["text"], "score": hook["score"],
                              "predictions": res}, indent=2, ensure_ascii=False))
        else:
            _print_predictions(hook["text"], res, args.json, rank=hook["rank"])
    cal = calibrate_from_actuals(conn)
    if not args.json:
        print(f"\n[feedback] {cal.get('message', cal.get('status'))}")
    return 0


def _print_predictions(hook: str, res: dict, as_json: bool,
                       rank: int | None = None) -> None:
    if as_json:
        print(json.dumps({"rank": rank, "hook": hook, "predictions": res},
                         indent=2, ensure_ascii=False))
        return
    prefix = f"{rank}. " if rank else ""
    print(f"\n{prefix}{hook}")
    for h, r in res.items():
        z = r["z_pred"]
        zs = "n/a (no model)" if z is None else f"{z:+.2f} z"
        print(f"  {h:<4} predicted: {zs:<14} confidence: {r['confidence']}")
        for c in r["contributors"][:3]:
            if "contribution_z" in c:
                print(f"       {c['contribution_z']:+.2f}  {c['label']}")
            else:
                print(f"       imp {c['importance']:.3f}  {c['label']}")


def _benchmark_model_cli(conn, settings) -> int:
    import time
    import tracemalloc
    from miner.hook_learn import build_training_data, train

    n_lib = conn.execute("SELECT COUNT(*) FROM hook_library").fetchone()[0]
    n_tr = conn.execute("SELECT COUNT(*) FROM hook_training_examples").fetchone()[0]
    print(f"CORPUS: {n_lib} library hooks · {n_tr} training examples")

    t0 = time.perf_counter()
    tracemalloc.start()
    n = build_training_data(conn, settings, replace=True)
    t_build = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    print(f"BUILD: {n} rows in {t_build:.2f}s · peak {peak / 1e6:.1f} MB · "
          f"{n / t_build:.0f} rows/s")

    t0 = time.perf_counter()
    res = train(conn, settings)
    t_train = time.perf_counter() - t0
    _, peak2 = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"TRAIN: {t_train:.2f}s · peak {peak2 / 1e6:.1f} MB (target < 3 GB)")
    if res.get("status") != "trained":
        print(f"  {res.get('message')}")
        return 0
    for h, r in res["results"].items():
        print(f"  {h:>2}s  {r['kind']:<8} cv_rmse {r['cv_rmse']} "
              f"baseline {r['baseline_rmse']} improvement {r['cv_r2_vs_baseline']:+.1%}")
    import os
    d = resolve_path(load_settings()["paths"]["models"])
    if d.exists():
        for p in sorted(d.glob("hook_*s_v*.joblib")):
            print(f"  model: {p.name} ({os.path.getsize(p) / 1024:.0f} KB)")
    return 0


def _benchmark(conn) -> None:
    print("HOOK PIPELINE STATUS")
    for label, sql in [
        ("videos", "SELECT COUNT(*) FROM videos"),
        ("transcripts", "SELECT COUNT(*) FROM transcripts"),
        ("heatmaps", "SELECT COUNT(*) FROM heatmaps"),
        ("hook_library rows", "SELECT COUNT(*) FROM hook_library"),
        ("library with retention", "SELECT COUNT(*) FROM hook_library WHERE retention_10s IS NOT NULL"),
        ("hook_generations", "SELECT COUNT(*) FROM hook_generations"),
    ]:
        print(f"  {label:<24} {conn.execute(sql).fetchone()[0]}")


def _export_legacy(conn, settings) -> None:
    """Legacy JSON export (previously --export): kept for compatibility."""
    rows = conn.execute(
        """SELECT video_id, hook_text, title, outlier_score FROM hook_library
           ORDER BY outlier_score DESC NULLS LAST LIMIT 300""").fetchall()
    lib = [{"video_id": r["video_id"], "hook_text": r["hook_text"][:400],
            "title": r["title"], "outlier_score": r["outlier_score"]} for r in rows]
    dest = resolve_path(load_settings()["paths"]["reports"]) / "hooks_library.json"
    dest.write_text(json.dumps(lib, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[export] {len(lib)} hooks -> {dest}")


if __name__ == "__main__":
    sys.exit(main())