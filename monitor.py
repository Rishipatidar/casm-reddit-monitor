#!/usr/bin/env python3
"""
casm-reddit-monitor — personal, read-only Reddit keyword monitor.

Searches Reddit for a small list of scam / phishing / impersonation keywords
and stores matches in a local SQLite database for manual review. The script
never posts, comments, votes, messages, or moderates.

Usage:
    python monitor.py            # run forever, polling every N minutes
    python monitor.py --once     # run a single poll and exit
    python monitor.py --export matches.csv   # export stored matches to CSV
"""

import argparse
import csv
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import praw
import prawcore
import yaml

DB_PATH = "matches.db"
log = logging.getLogger("casm-monitor")


# ---------------------------------------------------------------- setup ----

def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("poll_interval_minutes", 60)
    cfg.setdefault("results_per_query", 25)
    cfg.setdefault("retention_days", 30)
    cfg.setdefault("subreddits", [])
    cfg.setdefault("keywords", [])
    return cfg


def make_reddit(cfg):
    """Read-only client using a 'script' app. Credentials come from env vars."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.")
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=cfg["user_agent"],
    )
    reddit.read_only = True  # enforce read-only: no write actions possible
    return reddit


def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS matches (
               fullname   TEXT PRIMARY KEY,   -- t3_xxx (post)
               subreddit  TEXT,
               title      TEXT,
               snippet    TEXT,
               url        TEXT,
               keyword    TEXT,
               created_utc REAL,
               found_utc   REAL
           )"""
    )
    conn.commit()
    return conn


# --------------------------------------------------------------- polling ---

def snippet_of(text, length=280):
    text = (text or "").replace("\n", " ").strip()
    return text[:length]


def save(conn, post, keyword):
    conn.execute(
        """INSERT OR IGNORE INTO matches
           (fullname, subreddit, title, snippet, url, keyword, created_utc, found_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            post.fullname,
            str(post.subreddit),
            post.title,
            snippet_of(post.selftext),
            f"https://www.reddit.com{post.permalink}",
            keyword,
            post.created_utc,
            time.time(),
        ),
    )


def poll(reddit, conn, cfg):
    """One polling pass: site-wide search + watchlist subreddits."""
    limit = cfg["results_per_query"]
    # Two queries per keyword: site-wide, plus all watchlist subs combined
    # (e.g. "Scams+phishing+india"). 10 keywords x 2 x 24 polls = 480 req/day.
    targets = ["all"]
    if cfg["subreddits"]:
        targets.append("+".join(cfg["subreddits"]))
    before = conn.total_changes

    for keyword in cfg["keywords"]:
        for sub in targets:
            try:
                results = reddit.subreddit(sub).search(
                    f'"{keyword}"', sort="new", time_filter="week", limit=limit
                )
                for post in results:
                    save(conn, post, keyword)
            except prawcore.exceptions.PrawcoreException as e:
                log.warning("search failed (%s in r/%s): %s", keyword, sub, e)
            time.sleep(1)  # stay well under the rate limit
    conn.commit()
    log.info("poll complete: %d new matches", conn.total_changes - before)


# ------------------------------------------------------------- retention ---

def purge(reddit, conn, cfg):
    """Delete matches older than retention_days, and drop removed/deleted posts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cfg["retention_days"])).timestamp()
    conn.execute("DELETE FROM matches WHERE found_utc < ?", (cutoff,))

    fullnames = [r[0] for r in conn.execute("SELECT fullname FROM matches")]
    removed = []
    for i in range(0, len(fullnames), 100):  # info() accepts batches of 100
        batch = fullnames[i : i + 100]
        try:
            for post in reddit.info(fullnames=batch):
                if post.removed_by_category or post.selftext in ("[deleted]", "[removed]"):
                    removed.append(post.fullname)
        except prawcore.exceptions.PrawcoreException as e:
            log.warning("deletion check failed: %s", e)
    conn.executemany("DELETE FROM matches WHERE fullname = ?", [(f,) for f in removed])
    conn.commit()
    log.info("purge complete: %d deleted/removed posts dropped", len(removed))


# ---------------------------------------------------------------- export ---

def export_csv(conn, path):
    rows = conn.execute(
        "SELECT found_utc, keyword, subreddit, title, url, snippet FROM matches ORDER BY found_utc DESC"
    ).fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["found_at", "keyword", "subreddit", "title", "url", "snippet"])
        for found, kw, sub, title, url, snip in rows:
            w.writerow([datetime.fromtimestamp(found, timezone.utc).isoformat(), kw, sub, title, url, snip])
    print(f"Exported {len(rows)} matches to {path}")


# ------------------------------------------------------------------ main ---

def main():
    ap = argparse.ArgumentParser(description="Personal read-only Reddit keyword monitor")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--once", action="store_true", help="run one poll and exit")
    ap.add_argument("--export", metavar="CSV", help="export stored matches to CSV and exit")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(args.config)
    conn = init_db()

    if args.export:
        export_csv(conn, args.export)
        return

    reddit = make_reddit(cfg)
    last_purge = 0.0
    while True:
        poll(reddit, conn, cfg)
        if time.time() - last_purge > 24 * 3600:  # purge once a day
            purge(reddit, conn, cfg)
            last_purge = time.time()
        if args.once:
            break
        time.sleep(cfg["poll_interval_minutes"] * 60)


if __name__ == "__main__":
    main()
