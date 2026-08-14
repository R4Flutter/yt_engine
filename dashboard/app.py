"""VIRALFORGE dashboard (PLAN.md Phase 5, optional).

Streamlit app over the SQLite DB + reports/. Read-only, local:
  streamlit run dashboard/app.py

Tabs: Overview | Outliers | Patterns | Thumbnails | Scorecards | Feedback
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
    return channels, videos, my


def md_report_text() -> str:
    p = list(Path(ROOT / "reports").glob("patterns_*.md"))
    return p[-1].read_text(encoding="utf-8") if p else "(no report yet — run python -m miner.report)"


channels, videos, my = load()
reports_dir = ROOT / "reports"

st.title("📈 VIRALFORGE — Finance YouTube Viral Intelligence")
st.caption(f"DB: {load_settings()['paths']['db']} · channels {len(channels)} · outliers {len(videos)}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Outliers", "Patterns", "Thumbnails", "Scorecards"])

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

with tab5:
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