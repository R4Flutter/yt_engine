"""VIRALFORGE dashboard (PLAN.md Phase 5, optional).

Streamlit app over the SQLite DB + reports/. Read-only, local:
  streamlit run dashboard/app.py

Tabs: Overview | Outliers | Patterns | Hooks | Thumbnails | Scorecards | Feedback
"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from config import ROOT, load_settings
from db import get_connection

st.set_page_config(page_title="VIRALFORGE", page_icon="📈", layout="wide")


@st.cache_data(ttl=300)
def load():
    conn = get_connection()
    to_df = lambda cur: pd.DataFrame([dict(r) for r in cur])
    channels = to_df(conn.execute(
        "SELECT title, subs, niche_tag, median_views_30, video_count FROM channels ORDER BY subs DESC"))
    videos = to_df(conn.execute(
        """SELECT v.video_id, v.title, c.title AS channel, c.niche_tag, v.views, v.likes,
                  v.outlier_score, v.published_at, v.duration_sec,
                  vf.title_formula, vf.hook_archetype, vf.cuts_per_min, vf.thumb_word_count,
                  vf.thumb_contrast, vf.thumb_saturation, vf.thumb_has_face
           FROM videos v JOIN channels c ON c.channel_id = v.channel_id
           LEFT JOIN video_features vf ON vf.video_id = v.video_id
           WHERE v.outlier_score >= 5 ORDER BY v.outlier_score DESC"""))
    my = to_df(conn.execute(
        "SELECT id, file_path, score, iterations, published_video_id, actual_ctr, actual_avd_pct, actual_views_72h "
        "FROM my_videos ORDER BY id DESC"))
    hooks = to_df(conn.execute(
        """SELECT l.id, l.hook_text, l.channel, l.niche_tag, l.outlier_score,
                  l.archetype, l.opening_device, l.curiosity_mechanism,
                  l.emotional_mechanism, l.stakes_type, l.promise_type,
                  l.narrative_structure, l.retention_10s, l.early_retention,
                  l.retention_slope, l.hook_score, l.word_count, l.factuality,
                  v.title AS video_title
           FROM hook_library l LEFT JOIN videos v ON v.video_id = l.video_id
           WHERE l.hook_text IS NOT NULL
           ORDER BY l.hook_score DESC"""))
    gens = to_df(conn.execute(
        "SELECT id, topic, mode, duration_target, my_video_id, actual_ctr, "
        "actual_avd_pct, generated_at FROM hook_generations ORDER BY id DESC"))
    try:
        patterns = to_df(conn.execute(
            """SELECT pattern_key, scope, kind, feature, effect_z, ci95_lo,
                      ci95_hi, robust, channel_consistency, confidence,
                      n_videos, n_hooks, best_niche, best_duration_sec
               FROM learned_patterns
               ORDER BY ABS(effect_z) DESC"""))
    except Exception:
        patterns = None
    models = []
    mdir = load_settings()["paths"]["models"]
    mp = Path(mdir)
    if mp.exists():
        for meta in sorted(mp.glob("*.meta.json")):
            d = json.loads(meta.read_text(encoding="utf-8"))
            d["horizon"] = int(d.get("h") or d.get("horizon_s") or 0)
            d["version"] = Path(d.get("file", meta.name)).stem.split("_v")[-1]
            b, c = d.get("baseline_rmse"), d.get("cv_rmse")
            d["improvement_pct"] = (round((b - c) / b * 100, 1)
                                    if b and c is not None else 0.0)
            models.append(d)
    return channels, videos, my, hooks, gens, patterns, models


def md_report_text() -> str:
    p = list(Path(ROOT / "reports").glob("patterns_*.md"))
    return p[-1].read_text(encoding="utf-8") if p else "(no report yet — run python -m miner.report)"


channels, videos, my, hooks, gens, patterns, models = load()
reports_dir = ROOT / "reports"

st.title("📈 VIRALFORGE — Finance YouTube Viral Intelligence")
st.caption(f"DB: {load_settings()['paths']['db']} · channels {len(channels)} · outliers {len(videos)} · library hooks {len(hooks)}")

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    ["Overview", "Outliers", "Patterns", "Hooks", "Thumbnails", "Scorecards", "Feedback"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Channels tracked", len(channels))
    c2.metric("Outliers (≥5x)", len(videos))
    c3.metric("Median outlier lift", f"{videos['outlier_score'].median():.1f}x" if len(videos) else "n/a")
    c4.metric("Scorecards", len(my))
    st.subheader("Channels by subs")
    st.bar_chart(channels.set_index("title")["subs"])
    st.subheader("Outlier scores by niche")
    if len(videos):
        st.bar_chart(videos.groupby("niche_tag")["outlier_score"].median())

with tab2:
    st.subheader("Outlier leaderboard (≥5x channel median)")
    cols = ["title", "channel", "niche_tag", "views", "outlier_score", "title_formula", "hook_archetype"]
    st.dataframe(videos[cols].head(100), width="stretch", hide_index=True)

with tab3:
    st.subheader("Weekly pattern report")
    st.markdown(md_report_text())
    b = reports_dir / "benchmarks.json"
    if b.exists():
        st.subheader("Benchmarks (outlier percentiles)")
        st.json(json.loads(b.read_text(encoding="utf-8")))

with tab4:
    st.subheader("Hook intelligence engine (M3)")
    if not len(hooks):
        st.info("No hooks in library yet — run `python -m miner.hooks mine && "
                "python -m miner.hooks analyze && python -m miner.hooks build-library`")
    else:
        # ---- leaderboard
        st.markdown("#### Leaderboard (highest HookScore first)")
        cols = ["hook_text", "channel", "niche_tag", "hook_score", "outlier_score",
                "opening_device", "curiosity_mechanism", "stakes_type",
                "retention_10s", "early_retention", "factuality"]
        st.dataframe(hooks[cols].head(50), width="stretch", hide_index=True)

        # ---- DNA explorer
        st.markdown("#### DNA explorer")
        f1, f2 = st.columns(2)
        dev = f1.multiselect("Opening device", sorted(hooks["opening_device"].dropna().unique()))
        stk = f2.multiselect("Stakes", sorted(hooks["stakes_type"].dropna().unique()))
        exp = hooks
        if dev:
            exp = exp[exp["opening_device"].isin(dev)]
        if stk:
            exp = exp[exp["stakes_type"].isin(stk)]
        st.dataframe(exp[["hook_text", "channel", "opening_device",
                          "curiosity_mechanism", "emotional_mechanism",
                          "stakes_type", "promise_type", "narrative_structure"]],
                     width="stretch", hide_index=True)

        # ---- patterns
        st.markdown("#### Discovered patterns (effect sizes over videos)")
        hp = reports_dir / "hook_patterns.json"
        if hp.exists():
            d = json.loads(hp.read_text(encoding="utf-8"))
            st.json(d)
        else:
            st.info("Run `python -m miner.hooks patterns`")

    # ---- generator
    st.markdown("#### Generator")
    with st.form("hook_gen"):
        g1, g2, g3, g4 = st.columns(4)
        topic = g1.text_input("Topic", "Why Lamborghini makes so much money")
        mode = g2.selectbox("Mode", ["retention_optimized", "curiosity", "shock",
                                     "story", "investigation", "contrarian",
                                     "money", "emotional", "documentary", "fast",
                                     "authority", "mystery"])
        dur = g3.slider("Duration target (s)", 3, 30, 8)
        niche = g4.text_input("Niche (optional)", "finance")
        facts = st.text_input("Facts (comma-separated, e.g. 'made 2.8 billion dollars in 2023')")
        run = st.form_submit_button("Generate hooks")
    if run and topic:
        from miner.hook_gen import generate
        out = generate(get_connection(), topic, mode=mode, duration_target=dur,
                       facts=[f.strip() for f in facts.split(",") if f.strip()],
                       niche=niche or None)
        st.session_state["gen_out"] = out
    if st.session_state.get("gen_out"):
        gen = st.session_state["gen_out"]
        ev = gen.get("evidence_videos") or []
        if ev:
            st.caption(f"evidence: {len(ev)} retrieved hooks · "
                       f"{len({e.get('channel') for e in ev if e.get('channel')})} channels")
        for h in gen["hooks"][:5]:
            with st.expander(f"#{h['rank']} · score {h['score']} · {h['opening_device']} · {h['factuality']}"):
                st.write(h["text"])
                meta = [f"confidence: {h.get('confidence', '?')}"]
                if h.get("retention_projection") is not None:
                    meta.append(f"retention projection (z): {h['retention_projection']:+.2f}")
                if h.get("novelty_fallback"):
                    meta.append("novelty: ALL filtered → least-similar fallback")
                st.caption(" · ".join(meta))
                st.caption(f"why: {', '.join(h['why_it_works'])} · risks: {', '.join(h['risks'])}")
                if h.get("variants"):
                    st.caption(" | ".join(f"{k}s: {v}" for k, v in h["variants"].items()))
                pev = h.get("pattern_evidence")
                if pev and pev.get("matched"):
                    st.caption(f"pattern evidence: {pev['label']} "
                               f"(z {pev['effect_z']:+.2f}, {pev['confidence']}, {pev['scope']})")
                lr = h.get("learned")
                if lr and lr.get("z_pred") is not None:
                    st.caption(f"learned prediction: {lr['z_pred']:+.2f} z at 10s "
                               f"({lr['confidence']}, {lr.get('model_kind', '?')} model)")

    # ---- learned intelligence (M4)
    st.markdown("#### Learned intelligence (M4)")
    st.markdown("Retention is modeled per horizon (3/5/10/15/30s) with channel-grouped "
                "cross-validation. A model is kept only if it beats the corpus baseline "
                "by ≥5%; everything else is reported honestly as a baseline prediction "
                "with LOW confidence.")
    if models:
        mdf = pd.DataFrame(models)[["horizon", "kind", "version", "cv_rmse",
                                    "baseline_rmse", "improvement_pct",
                                    "trained_at", "n_videos"]]
        st.dataframe(mdf.sort_values("horizon"), width="stretch", hide_index=True)
    else:
        st.info("No models trained yet — run `python -m miner.hooks train --build`")
    if patterns is not None and len(patterns):
        st.dataframe(patterns[["pattern_key", "kind", "effect_z", "ci95_lo",
                               "ci95_hi", "confidence", "n_videos", "channel_consistency",
                               "best_duration_sec"]], width="stretch", hide_index=True)
    else:
        st.info("No learned patterns yet — run `python -m miner.hooks patterns-learned`")

    # ---- retention predictor
    st.markdown("#### Retention predictor")
    with st.form("hook_predict"):
        pred_text = st.text_input("Hook text to score",
                                  "Why does Lamborghini make so much money?")
        do_pred = st.form_submit_button("Predict retention")
    if do_pred and pred_text:
        from miner import hook_learn
        from miner.hook_dna import extract_dna
        dna = extract_dna(pred_text)
        rows = []
        for hz in (3, 5, 10, 15, 30):
            p = hook_learn.predict_dna(dna, hz)
            rows.append({"horizon_s": hz, "z_pred": p.get("z_pred"),
                         "confidence": p.get("confidence"),
                         "model_kind": p.get("model_kind")})
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        p10 = hook_learn.predict_dna(dna, 10)
        if p10.get("contributors"):
            st.caption("top contributors: " + ", ".join(
                f"{c['feature']} {c['contribution_z']:+.2f}"
                for c in p10["contributors"][:5]))

with tab5:
    st.subheader("Thumbnail benchmarks by niche")
    if len(videos) and videos["thumb_contrast"].notna().any():
        st.dataframe(videos.groupby("niche_tag").agg(
            n=("video_id", "count"),
            words_p50=("thumb_word_count", "median"),
            contrast_p50=("thumb_contrast", "median"),
            saturation_p50=("thumb_saturation", "median"),
            face_pct=("thumb_has_face", "mean"),
        ).round(1).style.format({"face_pct": "{:.0%}"}), width="stretch")
    else:
        st.info("No thumbnail metrics yet — run `python -m miner.thumbs`")

with tab6:
    st.subheader("Your videos — predicted vs actual")
    if len(my):
        st.dataframe(my, width="stretch", hide_index=True)
        with st.expander("How to get real CTR/AVD"):
            st.markdown("1. Publish via YouTube Studio (API uploads are private-locked).\n"
                        "2. `python -m feedback.analytics_pull` after setting up OAuth.\n"
                        "3. `python -m feedback.calibrate` once 10+ videos have actuals — "
                        "it reweights the scorecard categories.")
    else:
        st.info("No scorecards logged yet — run `python -m analyzer.score out/video.mp4 --title \"...\"`")
    w = reports_dir / "weights.json"
    if w.exists():
        st.subheader("Recalibrated weights (M7)")
        st.json(json.loads(w.read_text(encoding="utf-8")))

with tab7:
    st.subheader("Feedback loop — generated hooks vs published outcomes")
    if len(gens):
        st.dataframe(gens, width="stretch", hide_index=True)
        st.markdown("""
Link a published video to a generation:
`python -m miner.hooks record-outcome <gen_id> --my-video <my_video_id>`

Once 10+ generations have actuals, run `python -m feedback.calibrate` to reweight
the HookScore dimensions from observed performance instead of priors.
""")
    else:
        st.info("No generations logged yet — run `python -m miner.hooks generate \"topic\"`")