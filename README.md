# casm-reddit-monitor

A **personal, non-commercial, read-only** Reddit keyword monitor for security research.

It searches Reddit for a small list of scam, phishing and impersonation keywords and stores matching posts in a local SQLite database. I review matches manually and report genuine scams/impersonation through Reddit's standard report tools or to subreddit moderators.

## What it does

- Runs on my personal machine under my own account (u/RishiPr184), as a Reddit **script**-type OAuth app.
- Every 30–60 minutes, runs a keyword search across Reddit plus a small watchlist of subreddits (r/Scams, r/phishing, r/cybersecurity, r/india, r/IndiaTech).
- For each match, stores only: post URL, title, a short text snippet, timestamp and the matched keyword.
- Exports matches to CSV for a private local dashboard.

## What it does NOT do

- **No write actions of any kind.** The PRAW client is forced into `read_only` mode, so there's no posting, commenting, voting, messaging, chat, following or moderation.
- No user profiling, no collecting post histories, no bulk downloading or archiving.
- No AI/ML training on Reddit data.
- No commercial use. Data is not sold, shared or published.

## Rate limits and data handling

| Item | Setting |
|---|---|
| Request volume | < 500 requests/day, 1 s delay between requests |
| User-Agent | `script:casm-monitor:v1.0 (by /u/RishiPr184)` |
| Retention | Matches deleted after 30 days (configurable) |
| Deleted content | Posts that were deleted or removed on Reddit are purged daily |
| Storage | Local SQLite file only (`matches.db`, git-ignored) |

## Setup

```bash
git clone https://github.com/<your-username>/casm-reddit-monitor.git
cd casm-reddit-monitor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml      # edit keywords / subreddits

export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
```

Credentials are read from environment variables and are never stored in the repo.

## Usage

```bash
python monitor.py --once                 # single poll
python monitor.py                        # poll continuously
python monitor.py --export matches.csv   # export stored matches
```

## Compliance

This project follows Reddit's [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy), Developer Terms and Data API Terms. It's for personal use only.
