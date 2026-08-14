"""M3 Miner â€” hook mining (PLAN.md Section 5, M3.3).

Classifies the first-30s transcript of every outlier into an archetype and
estimates hook_promise_sec (seconds until the payoff promise is stated).

Usage:
  python -m miner.hooks
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from db import get_connection, init_db
from miner.llm import classify, classify_hook_archetype
from config import fix_console, load_settings, resolve_path

HOOK_ARCHETYPES = {
    "cold_open_stakes": "cold open with stakes in media res",
    "bold_claim": "bold claim / shocking number",
    "question": "rhetorical question",
    "story": "storytelling cold open",
    "stat": "stat-driven tease",
    "other": "other",
}


def heuristic_promise_sec(hook_text: str) -> float:
    """Heuristic: when does a concrete payoff/outcome word first appear."""
    payoff = re.compile(
        r"(today|in this video|by the end|you\'?ll|you will|let me show|the truth about|"
        r"how .{3,30} (lost|made|built|became|destroyed|collapsed)|the (real|actual|inside) story|"
        r"\$[\d,.]+\s*(million|billion|thousand)?)"
    )
    m = payoff.search(hook_text.lower())
    if not m:
        return 30.0
    words = re.findall(r"\S+", hook_text)
    return min(30.0, len(" ".join(words[: len(words) // 2])) * 0.1 if False else (words.index(m.group(1)) if m.group(1) in words else 15.0))


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", action="store_true", help="export hook library JSON (for M6 rewrites)")
    args = ap.parse_args()
    conn = get_connection()
    init_db(conn)
    rows = conn.execute(
        """SELECT t.video_id, t.hook_text
           FROM transcripts t JOIN videos v ON v.video_id = t.video_id
           WHERE t.hook_text IS NOT NULL AND length(t.hook_text) > 10"""
    ).fetchall()

    archetypes: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        arch = classify(
            f'Classify this first-30-seconds hook of a finance/business video into one of: '
            f'{", ".join(HOOK_ARCHETYPES.values())}. Reply with ONLY the category key.\nHook: {r["hook_text"][:400]}',
            fallback=classify_hook_archetype(r["hook_text"]),
        )
        conn.execute(
            """INSERT INTO video_features (video_id, hook_archetype) VALUES (?,?)
               ON CONFLICT(video_id) DO UPDATE SET hook_archetype=excluded.hook_archetype""",
            (r["video_id"], arch),
)
        archetypes[arch].append(r["video_id"])
    conn.commit()

    print(f"{'archetype':<20} {'n':>5}")
    print("-" * 30)
    for a, vids in sorted(archetypes.items(), key=lambda kv: -len(kv[1])):
        print(f"{a:<20} {len(vids):>5}")

    if args.export:
        lib = []
        for a, vids in archetypes.items():
            for vid in vids[:5]:
                row = conn.execute(
                    "SELECT t.hook_text, v.title, v.outlier_score FROM transcripts t "
                    "JOIN videos v ON v.video_id=t.video_id WHERE t.video_id=?",
                    (vid,),
                ).fetchone()
                if row and row["hook_text"]:
                    lib.append({
                        "archetype": a, "video_id": vid, "title": row["title"],
                        "outlier_score": row["outlier_score"],
                        "hook_text": row["hook_text"][:400],
                    })
        dest = resolve_path(load_settings()["paths"]["reports"]) / "hooks_library.json"
        dest.write_text(json.dumps(lib, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[hooks] library written {dest} ({len(lib)} examples)")


if __name__ == "__main__":
    main()
