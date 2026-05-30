#!/usr/bin/env python3
"""
Phan-o-meter X (Twitter) module.

Pulls recent Phillies fan posts from X via the v2 recent-search endpoint
(/2/tweets/search/recent), constrained to the pipeline's 24h lookback,
authenticated with the app-only OAuth 2.0 Bearer Token in X_BEARER_TOKEN.

Returns post dicts (text + metadata) for the twitter_fan voice. Mirrors
youtube.py's structure so phanometer.py wires it into main() the same way.

Usage:
    python twitter.py --search   # SMOKE TEST: one request, max_results=10
                                 # (~$0.05) — verifies auth + parsing cheaply.
                                 # The full per-run pull happens only via the
                                 # pipeline (phanometer.py); a bare invocation
                                 # here does nothing, to avoid accidental spend.
"""

# -----------------------------------------------------------------------------
# COST SAFETY — read before changing any cap
# -----------------------------------------------------------------------------
# X is pay-per-use, billed PER POST RETURNED (~$0.005/post), NOT per request.
# A $45/cycle spend cap is set in the X console as the platform backstop; this
# module is the in-code guard so a normal run never approaches it.
#
#   MAX_TWEETS_PER_RUN = 150 posts/run  ×  $0.005/post  =  ~$0.75/run
#   one run/day  →  ~$0.75/day  →  ~$22.50/month   (about half the $45 cap)
#
# Guards layered here:
#   - start_time pinned to the 24h lookback (matches the pipeline window), via
#     the recent-search endpoint (last-7-day index).
#   - "-is:retweet" in the query: you are not billed for duplicate retweet
#     content, and you get original fan voice. (X also dedups identical reads
#     within a 24h UTC window; -is:retweet is the cheaper guard.)
#   - HARD cap of MAX_TWEETS_PER_RUN posts across at most TWITTER_MAX_REQUESTS
#     pages. Pagination STOPS the instant the cap is reached — never unbounded.
#   - Each page requests only as many results as remain under the cap (X floor
#     is 10), so we never fetch — or pay for — more than the cap.
#   - The --search smoke test does a single max_results=10 page (~$0.05).
# -----------------------------------------------------------------------------

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# Query filtering happens at the QUERY level (not post-fetch) so excluded posts
# are never returned and therefore never billed — the same cost principle as
# -is:retweet. We filter:
#   -is:retweet  : duplicate retweet content (cheaper + original voice)
#   -is:reply    : reply-thread chatter (low-signal back-and-forth)
#   gambling vocab: brand names (-parlay -sportsbook -betmgm -draftkings
#     -fanduel) plus gambling-specific MULTIWORD phrases (-"vip lock"/-"vip
#     locks" — plural matters, X phrase match is exact-token; -"mlb script",
#     -"free pick"/-"free picks", -"best bet"). We deliberately do NOT exclude
#     bare common words (bet, lock, picks, odds, line, ML, card): they collide
#     with normal fan speech ("I'd bet Harper goes deep", "lock him up", "good
#     pickup", "5/30 card"). Brand names and gambling-specific phrases are safe;
#     generic words and abbreviations are not. (-"best bet" is the most generic
#     of the set — mild collision risk with "our best bet is to trade him";
#     watch it.) Note: this catches the brand/phrase spam styles but not daily
#     pick-card posts that use only abbreviations (ML, 1u, F5) — those would
#     need author/handle filtering, which is out of scope here.
#
# v1 KNOWN LIMITATION (media bleed): recent-search still returns media voice
# (beat writers, team/fan-brand accounts like Phillies Nation) mixed in with
# real fans. twitter_fan is meant for fan voice; for v1 we accept this media
# bleed and tag every result twitter_fan. (Gambling spam and reply noise are
# now filtered above; media bleed would need author/handle-based filtering,
# which is out of scope here.)
SEARCH_QUERY = (
    "(Phillies OR #RingTheBell) -is:retweet -is:reply lang:en "
    '-parlay -sportsbook -betmgm -draftkings -fanduel '
    '-"vip lock" -"vip locks" -"mlb script" -"free pick" -"free picks" -"best bet"'
)

TWITTER_LOOKBACK_HOURS = 24          # match the pipeline window
MAX_TWEETS_PER_RUN = 150             # HARD per-run cap — see COST SAFETY above
TWITTER_MAX_REQUESTS = 2             # bound pagination (cap is reached within)
PER_REQUEST_MAX_RESULTS = 100        # API allows 10..100; use the page max
SMOKE_TEST_MAX_RESULTS = 10          # --search: single page, ~$0.05
TWEET_CHAR_CAP = 400                 # per-post trim (mirrors reddit/youtube)


# -----------------------------------------------------------------------------
# Recent search (X API v2)
# -----------------------------------------------------------------------------
def _search_once(query, start_time, max_results, next_token=None):
    """One GET against /2/tweets/search/recent with the app-only Bearer Token."""
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        raise RuntimeError(
            "X_BEARER_TOKEN not set — add the app-only OAuth 2.0 Bearer Token "
            "to .env (see README Setup / .env.example)."
        )
    params = {
        "query": query,
        "start_time": start_time,
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics,lang",
    }
    if next_token:
        params["next_token"] = next_token
    url = f"{SEARCH_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def pull_tweets(lookback_hours_override=None, smoke_test=False):
    """Recent-search for Phillies fan posts, tagged to the twitter_fan voice.

    Hard-capped at MAX_TWEETS_PER_RUN posts across at most TWITTER_MAX_REQUESTS
    pages; pagination stops the instant the cap is hit (see COST SAFETY above).
    smoke_test=True does a single max_results=10 page (~$0.05) to verify auth
    and parsing cheaply.

    Returns a list of post dicts with a stable shape for phanometer.py to route
    into its own scoring section.
    """
    lookback = lookback_hours_override or TWITTER_LOOKBACK_HOURS
    start_time = (
        datetime.now(timezone.utc) - timedelta(hours=lookback)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"Pulling X posts ({lookback}h lookback)...")

    if not os.environ.get("X_BEARER_TOKEN"):
        print("  ! X_BEARER_TOKEN not set — skipping X ingestion")
        return []

    if smoke_test:
        cap, per_page, max_requests = SMOKE_TEST_MAX_RESULTS, SMOKE_TEST_MAX_RESULTS, 1
        print(f"  SMOKE TEST: one request, max_results={per_page} (~$0.05)")
    else:
        cap = MAX_TWEETS_PER_RUN
        per_page = PER_REQUEST_MAX_RESULTS
        max_requests = TWITTER_MAX_REQUESTS

    tweets = []
    next_token = None
    for _ in range(max_requests):
        remaining = cap - len(tweets)
        if remaining <= 0:
            break
        # Request only as many as remain under the cap (API floor is 10), so we
        # never fetch — or pay for — more than MAX_TWEETS_PER_RUN.
        page_size = max(10, min(per_page, remaining))
        try:
            resp = _search_once(SEARCH_QUERY, start_time, page_size, next_token)
        except Exception as e:
            print(f"  ! X search failed: {e}")
            break

        for t in resp.get("data", []):
            text = (t.get("text") or "").strip()
            if len(text) < 10:
                continue
            pm = t.get("public_metrics", {})
            tweets.append({
                "kind": "tweet",
                "voice": "twitter_fan",
                "text": text[:TWEET_CHAR_CAP],
                "tweet_id": t.get("id"),
                "created_at": t.get("created_at"),
                "likes": pm.get("like_count", 0),
                "retweets": pm.get("retweet_count", 0),
            })
            if len(tweets) >= cap:
                break

        next_token = resp.get("meta", {}).get("next_token")
        if not next_token:
            break

    print(f"  {len(tweets)} X post(s) (cap {cap})")
    return tweets


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    if "--search" in sys.argv:
        posts = pull_tweets(smoke_test=True)
        print(f"\n{len(posts)} post(s):")
        for p in posts:
            print(f"  ({p['likes']}♥ {p['retweets']}↻) {p['text'][:80]}")
    else:
        print("Usage: python twitter.py --search   # cheap smoke test (max 10 posts, ~$0.05)")
        print("The full per-run pull runs via the pipeline (phanometer.py), capped at "
              f"{MAX_TWEETS_PER_RUN} posts. A bare invocation here does nothing, to avoid spend.")
