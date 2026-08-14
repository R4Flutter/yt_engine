"""M3 topic mining (PLAN.md Section 5, M3 step 7).

TF-IDF + KMeans over outlier titles+descriptions; rank clusters by
average outlier score and size -> "hot topic list" for your next scripts.

Usage:
  python -m miner.topics                 # cluster outliers
  python -m miner.topics --k 6 --top 5   # custom cluster count, top words per cluster
"""
import argparse
import sys

from config import fix_console
from db import get_connection


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=5, help="number of clusters")
    ap.add_argument("--top", type=int, default=4, help="top words per cluster")
    args = ap.parse_args()
    conn = get_connection()

    rows = conn.execute(
        """SELECT v.video_id, v.title, COALESCE(v.description, '') AS description, v.outlier_score
           FROM videos v WHERE v.outlier_score >= 5"""
    ).fetchall()
    if len(rows) < args.k * 2:
        print(f"[topics] only {len(rows)} outliers — need >= {args.k*2} to cluster")
        return

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
    except ImportError:
        print("[topics] scikit-learn not installed: pip install scikit-learn", file=sys.stderr)
        sys.exit(1)

    import re
    stop = set("the a an and or of to in for on with how why what who this that is are was were it its "
               "he she they we you your my their his her him them us i me be been being do does did have has "
               "had not no but so at by from as into about out up down over under again further then once "
               "here there all any both each few more most other some such only own same than too very s t can "
               "will just don should now billion million dollars year years company companies make makes made "
               "making money really just video videos youtube china world truth market business".split())
    texts, scores, ids = [], [], []
    for r in rows:
        t = re.sub(r"[^a-z ]", " ", (r["title"] + " " + r["description"]).lower())
        t = " ".join(w for w in t.split() if len(w) > 2 and w not in stop)
        texts.append(t)
        scores.append(r["outlier_score"])
        ids.append(r["video_id"])
    if not any(texts):
        print("[topics] no usable text")
        return

    vec = TfidfVectorizer(max_features=2000, min_df=2)
    X = vec.fit_transform(texts)
    km = KMeans(n_clusters=min(args.k, len(rows)), random_state=0, n_init=10)
    labels = km.fit_predict(X)
    terms = vec.get_feature_names_out()

    clusters = []
    for c in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == c]
        w = sorted(
            (round(km.cluster_centers_[c][j], 4), terms[j])
            for j in range(X.shape[1]) if km.cluster_centers_[c][j] > 0
        )
        clusters.append({
            "n": len(idx),
            "avg_score": round(sum(scores[i] for i in idx) / len(idx), 1),
            "top_words": [t for _, t in w[-args.top:]],
            "videos": [ids[i] for i in idx],
        })
    clusters.sort(key=lambda c: (-c["avg_score"], -c["n"]))

    print(f"[topics] {len(rows)} outliers -> {len(clusters)} clusters")
    for c in clusters:
        print(f"  {c['top_words']}: n={c['n']} avg outlier score={c['avg_score']}x")
    return clusters


if __name__ == "__main__":
    main()