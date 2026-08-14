"""M3 Miner â€” title mining (PLAN.md Section 5, M3.2).

Stats + LLM formula classification over outliers vs non-outliers;
persists into video_features and prints lift per formula.

Usage:
  python -m miner.titles          # classify titles in DB, print formula lift table
"""
from collections import defaultdict

from config import fix_console
from db import get_connection, init_db
from miner.llm import TITLE_FORMULAS, classify, classify_title_formula, title_stats


def main():
    fix_console()
    conn = get_connection()
    init_db(conn)
    rows = conn.execute(
        """SELECT v.video_id, v.title, v.outlier_score
           FROM videos v WHERE v.title IS NOT NULL AND v.outlier_score IS NOT NULL"""
    ).fetchall()

    lifts: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        stats = title_stats(r["title"])
        formula = classify(
            f'Classify this YouTube finance/business video title into one of: '
            f'{", ".join(TITLE_FORMULAS.values())}. Reply with ONLY the category key.\nTitle: {r["title"]}',
            fallback=classify_title_formula(r["title"]),
        )
        conn.execute(
            """INSERT INTO video_features (video_id, title_len, title_word_count,
                 title_has_number, title_number_is_specific, title_uppercase_ratio, title_formula)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(video_id) DO UPDATE SET
                 title_len=excluded.title_len, title_word_count=excluded.title_word_count,
                 title_has_number=excluded.title_has_number,
                 title_number_is_specific=excluded.title_number_is_specific,
                 title_uppercase_ratio=excluded.title_uppercase_ratio,
                 title_formula=excluded.title_formula""",
            (r["video_id"], stats["len"], stats["word_count"], int(stats["has_number"]),
             int(stats["number_is_specific"]), stats["uppercase_ratio"], formula),
        )
        lifts[formula].append(r["outlier_score"])
    conn.commit()

    print(f"{'formula':<22} {'n':>5} {'med lift':>9} {'mean lift':>10}")
    print("-" * 50)
    for f, scores in sorted(lifts.items(), key=lambda kv: -len(kv[1])):
        med = sorted(scores)[len(scores) // 2]
        print(f"{f:<22} {len(scores):>5} {med:>9.2f} {sum(scores)/len(scores):>10.2f}")


if __name__ == "__main__":
    main()
