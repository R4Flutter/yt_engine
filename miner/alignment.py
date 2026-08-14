"""M3 — the alignment engine. The reason this project is worth building.

Every growth tool scores videos against folklore ("hook in 15 seconds", "4
words on a thumbnail"). YouTube's "Most Replayed" graph is a free, public,
second-by-second record of where real viewers actually stayed. Joined to the
word-timestamped transcript, it answers a question no blog post can:

    which SENTENCES hold finance viewers, and which lose them?

For each sentence we record the retention heat while it was spoken, and the
heat 10s later. Regressing sentence features on that gives measured effect
sizes for the niche — not advice, coefficients.

Confound control is the difference between a finding and a coincidence:
  * heat is z-scored WITHIN each video, so we learn about sentences, not about
    which videos happened to be popular
  * rel_pos is always in the model, so "intros get rewatched" cannot disguise
    itself as a language effect
  * cross-validation groups by CHANNEL, so we do not simply learn one
    narrator's verbal tics
  * effect sizes are bootstrapped over videos and reported with intervals;
    with tens of thousands of sentences everything is "significant"

Usage:
    python -m miner.alignment --align          # build the sentence table
    python -m miner.alignment --fit            # fit and report coefficients
    python -m miner.alignment --curve          # the canonical retention shape
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import numpy as np

from config import fix_console, load_settings
from db import get_connection, init_db

# --------------------------------------------------------------- lexicons
# Regex/lexicon rather than spaCy on purpose: this machine has ~1 GB of free
# RAM, and the features below need precision on finance language, not general
# NER. A 50 MB model would buy accuracy we do not need here.

CONTRAST = re.compile(r"\b(but|however|yet|although|though|instead|despite|until)\b", re.I)
CONSEQUENCE = re.compile(r"\b(so|therefore|because|which meant|thus|as a result|that's why)\b", re.I)
DOLLAR = re.compile(r"(\$\s?[\d,.]+|\b\d[\d,.]*\s?(dollars?|bucks)\b)", re.I)
PERCENT = re.compile(r"(\d+(\.\d+)?\s?%|\bpercent\b)", re.I)
DIGITS = re.compile(r"\d")
# Narration for TTS spells numbers out, so a digit regex alone reports a film
# about billions as containing no facts.
SPELLED = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|trillion)\b", re.I)
ROUND_NUM = re.compile(r"\b(\d+)(000|00)\b|\b(ten|hundred|thousand|million|billion)\b", re.I)
TITLES = re.compile(r"\b(mr|mrs|ms|dr|ceo|founder|president|chairman|billionaire|investor)\b", re.I)
ORG_HINT = re.compile(
    r"\b(inc|corp|corporation|company|bank|group|holdings|ventures|capital|fund|llc|ltd)\b", re.I)
ABSTRACT = re.compile(
    r"^(the\s+)?(economy|market|value|growth|inflation|system|industry|concept|idea|"
    r"problem|situation|process|strategy|business model)\b", re.I)
# Capitalized token that is not sentence-initial -> proper noun candidate.
PROPER = re.compile(r"(?<!^)(?<![.!?]\s)\b([A-Z][a-zA-Z]{2,})\b")

STOP_CAPS = {"I", "The", "But", "And", "So", "It", "This", "That", "He", "She", "They",
             "We", "You", "In", "On", "At", "If", "When", "What", "Why", "How", "Now"}


# ------------------------------------------------------------------ curves

def resample_curve(points: list[dict], duration: float) -> np.ndarray | None:
    """yt-dlp heatmap segments -> one heat value per second."""
    if not points or duration < 1:
        return None
    xs, ys = [], []
    for p in points:
        s, e, v = p.get("start_time"), p.get("end_time"), p.get("value")
        if s is None or v is None:
            continue
        xs.append((float(s) + float(e if e is not None else s)) / 2.0)
        ys.append(float(v))
    if len(xs) < 5:
        return None
    order = np.argsort(xs)
    xs, ys = np.array(xs)[order], np.array(ys)[order]
    return np.interp(np.arange(int(duration), dtype=float), xs, ys)


# --------------------------------------------------------------- sentences

MIN_WORDS = 6      # below this it is a caption fragment, not an utterance
MAX_WORDS = 40     # above this we are running two thoughts together


def sentences_from_words(words: list[dict], gap: float) -> list[dict]:
    """Group word events into utterances.

    YouTube auto-captions carry NO punctuation — measured on this corpus, only
    1.1% of word tokens end in .!? — so terminal punctuation cannot be the
    boundary rule. Pause length is all we have.

    The threshold is empirical, not assumed. On this corpus the word-gap p95 is
    0.80s, and that is the value that yields ~19 words per unit, which is the
    length of a real spoken sentence. Splitting at the p75 (0.40s) produces
    5-word fragments and a model fitted on those learns nothing about language.

    Because the gap distribution has a cliff just above 0.8s, the pause rule
    alone is fragile: MIN_WORDS stops a stray pause from emitting a fragment,
    and MAX_WORDS stops a transcript with no long pauses from emitting a single
    600-word blob.
    """
    out: list[dict] = []
    buf: list[dict] = []

    def flush(end_time: float) -> None:
        if not buf:
            return
        t0 = float(buf[0].get("start", 0))
        text = " ".join((b.get("text") or "").strip() for b in buf).strip()
        if text:
            out.append({"t_start": t0, "t_end": max(end_time, t0 + 0.3),
                        "text": text, "word_count": len(buf)})
        buf.clear()

    for i, w in enumerate(words):
        text = (w.get("text") or "").strip()
        if not text:
            continue
        buf.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None:
            flush(float(w.get("start", 0)) + 2.0)
            break
        pause = float(nxt.get("start", 0)) - float(w.get("start", 0))
        punctuated = text[-1] in ".!?"          # rare here, but Whisper punctuates
        if (len(buf) >= MIN_WORDS and (pause > gap or punctuated)) or len(buf) >= MAX_WORDS:
            flush(float(nxt.get("start", 0)))
    return out


def featurize(sents: list[dict], duration: float) -> list[dict]:
    """Deterministic sentence features. No LLM, no model download."""
    seen_entities: set[str] = set()
    last_entity_t = 0.0
    last_number_t = 0.0
    prev_len = None

    for s in sents:
        txt = s["text"]
        dur = max(0.3, s["t_end"] - s["t_start"])
        s["wpm"] = round(s["word_count"] / dur * 60, 1)
        s["rel_pos"] = round(s["t_start"] / duration, 4) if duration else 0.0

        has_dollar = bool(DOLLAR.search(txt))
        has_num = bool(DIGITS.search(txt) or SPELLED.search(txt))
        s["has_dollar"] = int(has_dollar)
        s["has_number"] = int(has_num)
        s["has_percent"] = int(bool(PERCENT.search(txt)))
        # "Specific" = carries a number that does not read as a round estimate.
        # $10,427 reads as real; $10,000 reads as marketing.
        s["number_specific"] = int(has_num and not ROUND_NUM.search(txt))
        s["is_question"] = int(txt.rstrip().endswith("?"))
        s["is_contrast"] = int(bool(CONTRAST.search(txt)))
        s["is_consequence"] = int(bool(CONSEQUENCE.search(txt)))

        proper = {m for m in PROPER.findall(txt) if m not in STOP_CAPS}
        s["names_person"] = int(bool(TITLES.search(txt)) or len(proper) > 0)
        s["names_org"] = int(bool(ORG_HINT.search(txt)))
        fresh = proper - seen_entities
        s["new_entity"] = int(bool(fresh))
        s["abstract_subj"] = int(bool(ABSTRACT.match(txt.strip())))

        s["sec_since_entity"] = round(s["t_start"] - last_entity_t, 2)
        s["sec_since_number"] = round(s["t_start"] - last_number_t, 2)
        s["len_delta"] = float(s["word_count"] - prev_len) if prev_len is not None else 0.0

        if proper:
            seen_entities |= proper
            last_entity_t = s["t_start"]
        if has_num:
            last_number_t = s["t_start"]
        prev_len = s["word_count"]
    return sents


def attach_heat(sents: list[dict], curve: np.ndarray, lookahead: int) -> list[dict]:
    """Join each sentence to the retention heat while it was spoken.

    heat_z is normalized within the video: absolute heat mostly reflects how
    popular the video is, which would just teach the model that popular videos
    are popular.
    """
    mu, sd = float(curve.mean()), float(curve.std()) or 1e-6
    n = len(curve)
    for s in sents:
        a, b = int(s["t_start"]), max(int(s["t_end"]), int(s["t_start"]) + 1)
        if a >= n:
            s["heat"] = s["heat_delta"] = s["heat_z"] = None
            continue
        here = float(curve[a:min(b, n)].mean())
        after_slice = curve[min(b, n):min(b + lookahead, n)]
        after = float(after_slice.mean()) if len(after_slice) else here
        s["heat"] = round(here, 4)
        s["heat_delta"] = round(after - here, 4)
        s["heat_z"] = round((here - mu) / sd, 4)
    return sents


COLS = ["video_id", "idx", "t_start", "t_end", "text", "word_count", "wpm",
        "heat", "heat_delta", "heat_z", "rel_pos", "has_dollar", "has_number",
        "number_specific", "has_percent", "is_question", "is_contrast",
        "is_consequence", "names_person", "names_org", "new_entity",
        "abstract_subj", "sec_since_entity", "sec_since_number", "len_delta"]

FEATURES = ["rel_pos", "has_dollar", "has_number", "number_specific", "has_percent",
            "is_question", "is_contrast", "is_consequence", "names_person",
            "names_org", "new_entity", "abstract_subj", "sec_since_entity",
            "sec_since_number", "word_count", "wpm", "len_delta"]

LABEL_NAMES = {
    "rel_pos": "position in video (control)",
    "has_dollar": "states a dollar amount",
    "has_number": "carries any number",
    "number_specific": "specific (non-round) number",
    "has_percent": "states a percentage",
    "is_question": "asks a question",
    "is_contrast": "contrast (but / however)",
    "is_consequence": "consequence (so / therefore)",
    "names_person": "names a person",
    "names_org": "names a company",
    "new_entity": "introduces a NEW entity",
    "abstract_subj": "abstract subject ('the economy')",
    "sec_since_entity": "seconds since last new entity",
    "sec_since_number": "seconds since last number",
    "word_count": "sentence length (words)",
    "wpm": "delivery speed (wpm)",
    "len_delta": "length change vs previous sentence",
}


# ------------------------------------------------------------------- align

def align_all(conn, settings, rebuild: bool = False) -> int:
    cfg = settings["align"]
    rows = conn.execute(
        """SELECT v.video_id, v.duration_sec, h.points_json, t.words_json
           FROM videos v JOIN heatmaps h USING(video_id) JOIN transcripts t USING(video_id)
           WHERE v.duration_sec >= ? AND t.words_json IS NOT NULL""",
        (cfg["min_duration_sec"],)).fetchall()

    if rebuild:
        conn.execute("DELETE FROM sentences")
    done = {r[0] for r in conn.execute("SELECT DISTINCT video_id FROM sentences")}

    total = 0
    for r in rows:
        vid = r["video_id"]
        if vid in done:
            continue
        try:
            points = json.loads(r["points_json"])
            words = json.loads(r["words_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        curve = resample_curve(points, r["duration_sec"])
        if curve is None:
            continue
        sents = sentences_from_words(words, cfg["sentence_gap_sec"])
        if len(sents) < cfg["min_sentences"]:
            continue
        sents = attach_heat(featurize(sents, float(r["duration_sec"])), curve,
                            cfg["heat_lookahead_sec"])

        payload = [tuple([vid, i] + [s.get(c) for c in COLS[2:]])
                   for i, s in enumerate(sents) if s.get("heat_z") is not None]
        conn.executemany(
            f"INSERT INTO sentences ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
            payload)
        conn.commit()
        total += len(payload)
        print(f"  {vid}  {len(payload):4d} sentences")
    return total


# --------------------------------------------------------------------- fit

def fit(conn, settings) -> dict:
    """Ridge on standardized features, grouped by channel, bootstrapped by video.

    Ridge rather than gradient boosting because the deliverable is an
    interpretable effect size per feature. A tree ensemble would predict
    marginally better and tell you nothing you could write into a script.
    """
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler

    rows = conn.execute(
        f"""SELECT s.video_id, v.channel_id, s.heat_z, {','.join('s.' + f for f in FEATURES)}
            FROM sentences s JOIN videos v USING(video_id)
            WHERE s.heat_z IS NOT NULL""").fetchall()
    if len(rows) < 500:
        raise SystemExit(f"Only {len(rows)} aligned sentences. Run --align, and deep-crawl more "
                         f"videos first (python -m harvester.deep_crawl --top 40).")

    y_raw = np.array([float(r["heat_z"]) for r in rows])
    videos = np.array([r["video_id"] for r in rows])
    channels = np.array([r["channel_id"] for r in rows])
    rel = np.array([float(r["rel_pos"] or 0) for r in rows])

    # --- residualize on position BEFORE looking at language ------------------
    # Retention against position is a sharp spike at 0% then a slow decay, so a
    # linear rel_pos term cannot absorb it and the leftover position signal
    # leaks into whichever language features happen to cluster near the intro.
    # Binning is the honest fix: subtract the corpus-wide mean heat at each
    # point in the runtime, and model what is left. The question then becomes
    # the one worth asking -- "given WHERE we are in the video, did this line
    # do better or worse than expected?"
    n_bins = 50
    bin_idx = np.clip((rel * n_bins).astype(int), 0, n_bins - 1)
    pos_curve = np.array([y_raw[bin_idx == b].mean() if (bin_idx == b).any() else 0.0
                          for b in range(n_bins)])
    y = y_raw - pos_curve[bin_idx]

    # rel_pos is now absorbed into the target, so keep it out of the design
    # matrix -- leaving it in would let the model re-fit what we just removed.
    feats = [f for f in FEATURES if f != "rel_pos"]
    X = np.array([[float(r[f] if r[f] is not None else 0) for f in feats] for r in rows])
    Xs = StandardScaler().fit_transform(X)

    # Held-out R^2, grouped by channel: can this generalize to a narrator it
    # has never heard?
    n_groups = len(set(channels))
    scores = []
    if n_groups >= 3:
        gkf = GroupKFold(n_splits=min(5, n_groups))
        for tr, te in gkf.split(Xs, y, groups=channels):
            m = Ridge(alpha=1.0).fit(Xs[tr], y[tr])
            scores.append(m.score(Xs[te], y[te]))

    # Bootstrap over videos (not sentences): sentences within a video are
    # correlated, so resampling sentences would produce intervals that are far
    # too narrow.
    uniq = np.unique(videos)
    boot = []
    rng = np.random.default_rng(42)
    for _ in range(400):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        idx = np.concatenate([np.where(videos == v)[0] for v in pick])
        boot.append(Ridge(alpha=1.0).fit(Xs[idx], y[idx]).coef_)
    boot = np.array(boot)

    full = Ridge(alpha=1.0).fit(Xs, y)
    coefs = []
    for i, f in enumerate(feats):
        lo, hi = np.percentile(boot[:, i], [2.5, 97.5])
        coefs.append({
            "feature": f, "label": LABEL_NAMES[f],
            "effect": round(float(full.coef_[i]), 4),
            "ci": [round(float(lo), 4), round(float(hi), 4)],
            "robust": bool(lo > 0 or hi < 0),   # interval excludes zero
        })
    coefs.sort(key=lambda c: -abs(c["effect"]))

    return {
        "n_sentences": len(rows), "n_videos": len(uniq), "n_channels": n_groups,
        "cv_r2_by_channel": round(float(np.mean(scores)), 4) if scores else None,
        "target": "heat_z residualized on position (50 bins)",
        "position_curve": [round(float(v), 4) for v in pos_curve],
        "confidence": "high" if len(uniq) >= settings["align"]["min_videos_for_findings"] else "low",
        "coefficients": coefs,
    }


def canonical_curve(conn, niche: str | None = None) -> dict:
    """The average retention SHAPE of outliers — the curve to imitate."""
    q = """SELECT h.points_json, v.duration_sec, v.niche_tag FROM heatmaps h
           JOIN videos v USING(video_id) JOIN channels c USING(channel_id)
           WHERE v.duration_sec > 120"""
    rows = conn.execute(q.replace("v.niche_tag", "c.niche_tag")).fetchall()
    curves = []
    for r in rows:
        if niche and r["niche_tag"] != niche:
            continue
        c = resample_curve(json.loads(r["points_json"]), r["duration_sec"])
        if c is None or len(c) < 60:
            continue
        # time-normalize to 100 points so videos of different lengths compare
        curves.append(np.interp(np.linspace(0, len(c) - 1, 100), np.arange(len(c)), c))
    if not curves:
        return {}
    arr = np.array(curves)
    return {"n": len(curves), "mean": [round(float(x), 4) for x in arr.mean(axis=0)],
            "p25": [round(float(x), 4) for x in np.percentile(arr, 25, axis=0)],
            "p75": [round(float(x), 4) for x in np.percentile(arr, 75, axis=0)]}


def sparkline(vals: list[float]) -> str:
    blocks = " ▁▂▃▄▅▆▇█"
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    return "".join(blocks[min(8, int((v - lo) / rng * 8))] for v in vals)


def main() -> None:
    fix_console()
    ap = argparse.ArgumentParser(description="VIRALFORGE alignment engine")
    ap.add_argument("--align", action="store_true", help="build the sentence table")
    ap.add_argument("--rebuild", action="store_true", help="wipe and rebuild sentences")
    ap.add_argument("--fit", action="store_true", help="fit and report coefficients")
    ap.add_argument("--curve", action="store_true", help="canonical retention shape")
    args = ap.parse_args()
    if not any([args.align, args.fit, args.curve, args.rebuild]):
        args.align = args.fit = True

    settings = load_settings()
    conn = get_connection()
    init_db(conn)

    if args.align or args.rebuild:
        n = align_all(conn, settings, rebuild=args.rebuild)
        total = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        print(f"\nAligned {n} new sentences · {total} total in corpus\n")

    if args.curve:
        cc = canonical_curve(conn)
        if cc:
            print(f"Canonical retention shape (n={cc['n']} videos, 0% -> 100% of runtime)")
            print("  " + sparkline(cc["mean"]))
            print(f"  opening 10%: {np.mean(cc['mean'][:10]):.3f}   "
                  f"middle: {np.mean(cc['mean'][40:60]):.3f}   "
                  f"final 10%: {np.mean(cc['mean'][-10:]):.3f}\n")

    if args.fit:
        res = fit(conn, settings)
        print(f"RETENTION COEFFICIENTS  (n={res['n_sentences']:,} sentences, "
              f"{res['n_videos']} videos, {res['n_channels']} channels)")
        print(f"held-out R2 across channels: {res['cv_r2_by_channel']}   "
              f"confidence: {res['confidence'].upper()}")
        print(f"\n{'effect':>8}  {'95% CI':>18}  feature")
        print("-" * 72)
        for c in res["coefficients"]:
            mark = "*" if c["robust"] else " "
            ci = f"[{c['ci'][0]:+.3f},{c['ci'][1]:+.3f}]"
            print(f"{c['effect']:+8.4f}{mark} {ci:>18}  {c['label']}")
        print("\n* = 95% bootstrap interval (over videos) excludes zero")
        if res["confidence"] == "low":
            print(f"\nNOTE: {res['n_videos']} videos is below the {load_settings()['align']['min_videos_for_findings']}-video "
                  f"threshold.\n      Treat the ranking as a hypothesis, not a rule. Deep-crawl more videos.")

        out = load_settings()["paths"]["reports"]
        from config import resolve_path
        p = resolve_path(out) / "retention_coefficients.json"
        p.write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nWrote {p}")


if __name__ == "__main__":
    sys.exit(main())
