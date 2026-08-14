"""M7 feedback — pull your own channel's real CTR/retention (PLAN.md Section 5, M7).

Uses the free YouTube Analytics API for your OWN channel (OAuth2 required).
Videos uploaded via API are private-locked unless audited — upload manually.

Requirements (set once, ~15 min):
  1. Create OAuth2 credentials (Desktop app) in Google Cloud Console for the
     same project that has the Data API enabled.
  2. Save client_secret.json in this folder.
  3. Run:  python -m feedback.analytics_pull --init-token   (one-time browser auth)
  4. Then: python -m feedback.analytics_pull               (pulls last 90d)

Stores predicted-vs-actual rows in my_videos; prints the comparison.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from config import fix_console
from db import get_connection

HERE = Path(__file__).resolve().parent
CLIENT = HERE / "client_secret.json"
TOKEN = HERE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]


def _google_auth():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("pip install google-api-python-client google-auth-oauthlib", file=sys.stderr)
        sys.exit(1)
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        if not CLIENT.exists():
            print(f"client_secret.json missing — put OAuth2 desktop credentials in {HERE}", file=sys.stderr)
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def build_client():
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=_google_auth())


def fetch_reports(client, days: int = 90) -> list[dict]:
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    # per-video: impressions, CTR, AVD, views
    req = client.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
        dimensions="video", sort="-views", maxResults=50,
        filters="video==MINE",  # placeholder — replaced below if needed
    )
    try:
        resp = req.execute()
    except Exception as e:
        print(f"[analytics] query failed: {e}", file=sys.stderr)
        # per-video CTR needs impressions dimension data:
        req2 = client.reports().query(
            ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
            dimensions="video", sort="-views", maxResults=50,
        )
        resp = req2.execute()
    rows = []
    for r in resp.get("rows", []):
        hdrs = resp["columnHeaders"]
        rec = {h["name"]: v for h, v in zip(hdrs, r)}
        rec["video_id"] = rec.pop("video", None)
        rows.append(rec)
    return rows


def main():
    fix_console()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--init-token", action="store_true", help="one-time OAuth browser flow")
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()
    if args.init_token:
        _google_auth()
        print("[analytics] token saved — re-run without --init-token to pull")
        return

    client = build_client()
    rows = fetch_reports(client, args.days)
    if not rows:
        print("[analytics] no data in window (or channel has no views yet)")
        return
    conn = get_connection()
    for r in rows:
        conn.execute(
            """UPDATE my_videos SET actual_views_72h=?, actual_avd_pct=? WHERE published_video_id=?""",
            (int(r.get("views", 0)), float(r.get("averageViewPercentage", 0)), r["video_id"]),
        )
    conn.commit()
    print(f"[analytics] {len(rows)} videos with real data (last {args.days}d)")
    for r in rows[:10]:
        print(f"  {r['video_id']}: views={r.get('views')} AVD%={r.get('averageViewPercentage')}")


if __name__ == "__main__":
    main()