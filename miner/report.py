"""M3 Miner â€” weekly patterns report (PLAN.md Section 5, M3.8).

Assembles reports/patterns_YYYY-WW.md: outlier summary, title formula lift,
hook archetypes, heatmap peaks/dips, hot keywords.

Usage:
  python -m miner.report            # uses whatever is already in the DB
"""
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from statistics import median

from config import ROOT, fix_console, load_settings, resolve_path
from db import get_connection, init_db

STOPWORDS = set(
    "the a an and or of to in for on with this that his her their they he she it was were "
    "is are be been as at by from into over under how why what when where who which you your "
    "his its our their them then than so not no but do does did will would can could should "
    "has have had about after before because just like more most other some such only own same too"
    "very s t re ve ll m".split()
)


def _hot_keywords(conn, n=15):
    rows = conn.execute("SELECT title FROM videos WHERE outlier_score >= 5").fetchall()
    words = Counter()
    for r in rows:
        toks = re.findall(r"[A-Za-z]{4,}", r["title"])
        for t in toks:
            if t.lower() not in STOPWORDS:
                words[t.lower()] += 1
    return words.most_common(n)


def _heatmap_insights(conn, n=6):
    """Average normalized heat curve; report top peaks and dips across outliers."""
    curves = []
    for r in conn.execute("SELECT points_json FROM heatmaps").fetchall():
        pts = json.loads(r["points_json"])
        if isinstance(pts, list) and len(pts) >= 20:
            curves.append([float(p.get("value", 0)) for p in pts])
    if not curves:
        return None
    n = min(max(len(c) for c in curves), 100)
    avg = [sum(c[i * len(c) // n] for c in curves) / len(curves) for i in range(n)]
    return {"avg_curve_len": n, "peaks": f"top replay ~{int(avg.index(max(avg)) * 100 / n)}% of video",
            "dips": f"lowest replay ~{int(avg.index(min(avg)) * 100 / n)}% of video"}


def _percentiles(values, qs=(25, 50, 75, 90)):
    if not values:
        return {}
    s = sorted(values)
    out = {}
    for q in qs:
        idx = int(q / 100 * (len(s) - 1))
        out[f"p{q}"] = round(s[idx], 3)
    return out


def _benchmarks(conn) -> dict:
    """Percentiles among OUTLIERS per niche/format (PLAN M3.8 -> benchmarks.json)."""
    rows = conn.execute(
        """SELECT c.niche_tag, v.duration_sec, v.outlier_score
           FROM videos v JOIN channels c ON c.channel_id = v.channel_id
           WHERE v.outlier_score >= 5 AND v.duration_sec > 60 AND v.duration_sec < 3600"""
    ).fetchall()
    if not rows:
        return {}
    bench = {}
    for tag in sorted({r["niche_tag"] for r in rows}):
        subset = [r for r in rows if r["niche_tag"] == tag]
        fmt = "long"
        bench.setdefault(tag, {})[fmt] = {
            "duration_sec": _percentiles([r["duration_sec"] for r in subset]),
            "outlier_score": _percentiles([r["outlier_score"] for r in subset]),
        }
    return bench


def main():
    fix_console()
    settings = load_settings()
    conn = get_connection()
    init_db(conn)

    outliers = conn.execute(
        "SELECT COUNT(*) AS n, AVG(outlier_score) AS med FROM videos WHERE outlier_score >= 5"
    ).fetchone()
    formulas = conn.execute(
        """SELECT title_formula AS f, COUNT(*) AS n, AVG(v.outlier_score) AS lift
           FROM video_features vf JOIN videos v ON v.video_id = vf.video_id
           WHERE vf.title_formula IS NOT NULL GROUP BY 1 ORDER BY 3 DESC"""
    ).fetchall()
    hooks = conn.execute(
        """SELECT hook_archetype AS a, COUNT(*) AS n FROM video_features
           WHERE hook_archetype IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall()

    now = dt.datetime.now()
    med = f"{outliers['med']:.1f}" if outliers["med"] is not None else "n/a"
    md = [f"# VIRALFORGE Weekly Pattern Report — {now.strftime('%Y-W%W')}", ""]
    md += ["## Outliers", f"- {outliers['n']} outliers (score >= 5x channel median views), median outlier score {med}x", ""]
    md += ["## Title formulas (by median outlier lift)", "", "| formula | n | median lift |", "|---|---|---|"]
    for f in formulas:
        md.append(f"| {f['f']} | {f['n']} | {f['lift']:.2f}x |")
    md += ["", "## Hook archetypes (first 30s)", "", "| archetype | n |", "|---|---|"]
    for h in hooks:
        md.append(f"| {h['a']} | {h['n']} |")
    md += ["", "## Retention (heatmap)", ""]
    hm = _heatmap_insights(conn)
    md += [f"- {hm['peaks']}", f"- {hm['dips']}"] if hm else ["- (no heatmap data yet — run deep_crawl)"]
    md += ["", "## Hot keywords in outlier titles", ""]
    md += [" | ".join(f"**{w}** ({c})" for w, c in _hot_keywords(conn))] or "- (no data)"

    md += ["", "## Thumbnail benchmarks (outliers)", "",
           "| niche | n | words p50 | contrast p50 | saturation p50 | face % |", "|---|---|---|---|---|---|"]
    thumb_rows = conn.execute(
        """SELECT c.niche_tag, vf.thumb_word_count, vf.thumb_contrast, vf.thumb_saturation, vf.thumb_has_face
           FROM video_features vf JOIN videos v ON v.video_id=vf.video_id
           JOIN channels c ON c.channel_id=v.channel_id WHERE vf.thumb_contrast IS NOT NULL"""
    ).fetchall()
    if thumb_rows:
        for tag in sorted({r["niche_tag"] for r in thumb_rows}):
            sub = [r for r in thumb_rows if r["niche_tag"] == tag]
            wc = [r["thumb_word_count"] for r in sub if r["thumb_word_count"] is not None]
            con = [r["thumb_contrast"] for r in sub]
            sat = [r["thumb_saturation"] for r in sub]
            faces = sum(1 for r in sub if r["thumb_has_face"])
            md.append(f"| {tag} | {len(sub)} | {median(wc) if wc else 'n/a'} | {median(con):.0f} | "
                      f"{median(sat):.0f} | {100*faces/len(sub):.0f}% |")
    else:
        md.append("| (run `python -m miner.thumbs`) | | | | | |")

    md += ["", "## Hot topics (outlier clusters, avg outlier score)", ""]
    try:
        from miner.topics import main as _t  # noqa: F401 — reuse cluster output
        import subprocess
        out = subprocess.run([sys.executable, "-m", "miner.topics"], capture_output=True,
                             text=True, env={**__import__("os").environ, "PYTHONPATH": str(ROOT)})
        for line in out.stdout.splitlines():
            if line.startswith("  "):
                md.append(f"- {line.strip()}")
    except Exception:
        md.append("- (run `python -m miner.topics`)")

    dest = resolve_path(settings["paths"]["reports"]) / f"patterns_{now.strftime('%Y-W%W')}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(md) + "\n", encoding="utf-8")
    bench = _benchmarks(conn)
    bench_path = dest.parent / "benchmarks.json"
    bench_path.write_text(json.dumps(bench, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[report] written {dest}")
    print(f"[report] written {bench_path} ({len(bench)} niches)")


if __name__ == "__main__":
    main()
