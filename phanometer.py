#!/usr/bin/env python3
"""
Phan-o-meter v1: Daily Phillies fan sentiment from r/phillies.

Pipeline:
  1. Pull last 24h of posts + comments from r/phillies (prioritize game threads)
  2. Score aggregate mood with Claude across 7 dimensions
  3. Compute reactive, baseline, and display scores
  4. Write data/YYYY-MM-DD.json and update data/history.json

Usage:
  python phanometer.py          # full run (Reddit + Claude)
  python phanometer.py --dry    # pull Reddit only, skip Claude (for testing)
"""

import os
import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from anthropic import Anthropic

from attendance import pull_attendance

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SUBREDDIT = "phillies"
LOOKBACK_HOURS = 24
MAX_POSTS = 50
MATCH_THREAD_COMMENT_CAP = 50
REGULAR_POST_COMMENT_CAP = 10
MODEL = "claude-sonnet-4-6"
DATA_DIR = Path("data")

# Dimension weights for the composite reactive score.
# Higher weight = dimension has more influence on the displayed number.
# Tune these based on what drives overall fan mood in practice.
DIMENSION_WEIGHTS = {
    "results_satisfaction": 1.5,   # Fans care about W/L most
    "front_office_trust":   0.8,
    "manager_confidence":   1.0,
    "lineup_confidence":    1.2,
    "pitching_confidence":  1.2,
    "health_outlook":       0.8,
    "postseason_belief":    1.0,
}

# Philly-voice mood taxonomy
MOOD_TIERS = [
    (90, "Red October"),
    (80, "Rally Towel"),
    (70, "Buzzing"),
    (60, "Good Vibes"),
    (50, "Cautious"),
    (40, "Uneasy"),
    (30, "Restless"),
    (20, "Boo-Bird"),
    (10, "Meltdown"),
    (0,  "Rock Bottom"),
]

def mood_label(score):
    for threshold, label in MOOD_TIERS:
        if score >= threshold:
            return label
    return "Rock Bottom"

# -----------------------------------------------------------------------------
# Reddit pull (via public JSON endpoints — no auth required)
# -----------------------------------------------------------------------------
MATCH_THREAD_KEYWORDS = ["game thread", "post game", "postgame", "pre game", "pregame"]
USER_AGENT = "phanometer/0.1 (daily Phillies sentiment tracker)"

def is_match_thread(title):
    t = title.lower()
    return any(kw in t for kw in MATCH_THREAD_KEYWORDS)

def _reddit_get(path, params=None):
    """Hit Reddit's public .json endpoints. No auth needed for public subreddits."""
    url = f"https://www.reddit.com{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)

def pull_reddit():
    cutoff = time.time() - LOOKBACK_HOURS * 3600
    items = []

    # 1. Get the newest posts from the subreddit
    listing = _reddit_get(f"/r/{SUBREDDIT}/new.json", {"limit": MAX_POSTS})
    posts = [child["data"] for child in listing["data"]["children"]]

    for post in posts:
        if post.get("created_utc", 0) < cutoff:
            continue

        title = post["title"]
        match = is_match_thread(title)
        items.append({
            "kind": "post",
            "title": title,
            "body": (post.get("selftext") or "")[:500],
            "score": post.get("score", 0),
            "created_utc": post["created_utc"],
            "is_match_thread": match,
        })

        # 2. Pull top comments for each post. Match threads get a bigger budget.
        cap = MATCH_THREAD_COMMENT_CAP if match else REGULAR_POST_COMMENT_CAP
        post_id = post["id"]
        try:
            comment_data = _reddit_get(
                f"/r/{SUBREDDIT}/comments/{post_id}.json",
                {"limit": cap, "sort": "top"},
            )
            # comment_data is [post_listing, comment_listing]
            comment_children = comment_data[1]["data"]["children"]
            for child in comment_children[:cap]:
                c = child.get("data", {})
                body = (c.get("body") or "").strip()
                if not body or body in ("[deleted]", "[removed]") or len(body) < 10:
                    continue
                if c.get("created_utc", 0) < cutoff:
                    continue
                items.append({
                    "kind": "comment",
                    "parent_title": title,
                    "body": body[:400],
                    "score": c.get("score", 0),
                    "created_utc": c["created_utc"],
                })
            time.sleep(1.0)  # Be polite — stay well under 60 req/min unauthenticated limit
        except Exception as e:
            print(f"  ! error fetching comments for '{title[:40]}': {e}")

    return items

# -----------------------------------------------------------------------------
# Scoring with Claude
# -----------------------------------------------------------------------------
SCORING_PROMPT = """You are analyzing Philadelphia Phillies fan sentiment from Reddit.

Below are posts and comments from r/phillies from the last 24 hours. Score the aggregate fan mood across seven dimensions.

Return ONLY a valid JSON object with this exact schema. No preamble, no markdown, no code fences.

{
  "dimensions": {
    "results_satisfaction": <int 0-100>,
    "front_office_trust":   <int 0-100>,
    "manager_confidence":   <int 0-100>,
    "lineup_confidence":    <int 0-100>,
    "pitching_confidence":  <int 0-100>,
    "health_outlook":       <int 0-100>,
    "postseason_belief":    <int 0-100>
  },
  "dimension_confidence": {
    "results_satisfaction": <int 0-100>,
    "front_office_trust":   <int 0-100>,
    "manager_confidence":   <int 0-100>,
    "lineup_confidence":    <int 0-100>,
    "pitching_confidence":  <int 0-100>,
    "health_outlook":       <int 0-100>,
    "postseason_belief":    <int 0-100>
  },
  "themes": [
    {"name": "<short phrase>", "delta": <int -10 to +10>, "sample": "<one-line summary>"}
  ],
  "quotes": [
    {"text": "<quote under 20 words>", "score": <int 0-100>, "source_hint": "<short context>"}
  ],
  "reasoning": "<2-3 sentences on what's driving today's mood>"
}

Scoring guide:
- 100 = maximum positive fan feeling on that dimension
- 50  = neutral / balanced / mixed
- 0   = maximum negative / despair
- dimension_confidence = how much signal on that dimension did you actually see in the content? 0 = barely mentioned, 100 = heavily discussed
- health_outlook uses HIGHER = fewer/less-severe injury concerns (inverted from intuitive "anxiety")
- 3-5 themes capturing what fans actually discussed today
- 3-4 representative quotes spanning the mood spectrum

Rules:
- Do NOT score individual players (no "Harper: 80", "Bohm: 20"). Focus on dimensions and themes.
- Ignore off-topic content (Eagles, Sixers, random memes, unrelated posts)
- Be honest: if the mood is bad, reflect it; don't manufacture optimism

Content to analyze:
"""

def format_content_for_scoring(items):
    # Sort: match threads first, then by upvote score, most-engaged first
    items_sorted = sorted(
        items,
        key=lambda x: (not x.get("is_match_thread", False), -x.get("score", 0)),
    )
    lines = []
    for item in items_sorted:
        if item["kind"] == "post":
            prefix = "[MATCH THREAD POST]" if item.get("is_match_thread") else "[POST]"
            body = f': {item["body"]}' if item["body"] else ""
            lines.append(f'{prefix} ({item["score"]}⬆) "{item["title"]}"{body}')
        else:
            lines.append(f'[COMMENT on "{item["parent_title"][:60]}"] ({item["score"]}⬆): {item["body"]}')
    return "\n".join(lines)

def score_with_claude(items):
    client = Anthropic()
    content = format_content_for_scoring(items)
    prompt = SCORING_PROMPT + content

    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    # Strip code fences defensively even though the prompt forbids them
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.rstrip().endswith("```"):
            raw = raw.rsplit("```", 1)[0]

    return json.loads(raw.strip())

# -----------------------------------------------------------------------------
# Composite scoring
# -----------------------------------------------------------------------------
def compute_reactive_score(dimensions, confidence):
    """Weighted avg of dimension scores, each weighted by (dim weight * confidence)."""
    total_weight = 0.0
    weighted_sum = 0.0
    for dim, score in dimensions.items():
        w = DIMENSION_WEIGHTS.get(dim, 1.0) * (confidence.get(dim, 50) / 100)
        weighted_sum += score * w
        total_weight += w
    if total_weight == 0:
        return 50
    return round(weighted_sum / total_weight)

def compute_baseline(history):
    """EWMA of prior reactive scores, alpha=0.3, last 30 days."""
    if not history:
        return None
    recent = history[-30:]
    alpha = 0.3
    baseline = recent[0]["reactive_score"]
    for day in recent[1:]:
        baseline = alpha * day["reactive_score"] + (1 - alpha) * baseline
    return round(baseline)

def compute_display_score(reactive, baseline, volume):
    """Blend reactive vs baseline. More volume → trust today's reactive number more."""
    if baseline is None:
        return reactive  # bootstrap — no history yet
    reactive_weight = min(0.7, 0.3 + volume / 500.0)
    return round(reactive_weight * reactive + (1 - reactive_weight) * baseline)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    dry_run = "--dry" in sys.argv
    DATA_DIR.mkdir(exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[{today}] Phan-o-meter daily run{' (DRY)' if dry_run else ''}")

    # 1. Pull Reddit
    print(f"Pulling r/{SUBREDDIT}...")
    items = pull_reddit()
    n_posts = sum(1 for i in items if i["kind"] == "post")
    n_comments = sum(1 for i in items if i["kind"] == "comment")
    n_match = sum(1 for i in items if i.get("is_match_thread"))
    print(f"  {len(items)} items: {n_posts} posts ({n_match} match threads), {n_comments} comments")

    if dry_run:
        print("\nDry run — skipping Claude. First 3 items:")
        for item in items[:3]:
            print(f"  - {item}")
        return

    if len(items) < 5:
        print("  ! Very low volume — results may be unreliable")

    # 2. Score with Claude
    print(f"Scoring with {MODEL}...")
    result = score_with_claude(items)

    # 3. Load history and compute composite
    history_path = DATA_DIR / "history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    # Exclude today from history if re-running same day (idempotency)
    history = [h for h in history if h["date"] != today]

    dimensions = result["dimensions"]
    confidence = result["dimension_confidence"]
    reactive = compute_reactive_score(dimensions, confidence)
    baseline = compute_baseline(history)
    display = compute_display_score(reactive, baseline, len(items))

    # 4. Pull attendance (independent hard signal, not a scoring dimension)
    print("Pulling attendance from MLB Stats API...")
    try:
        attendance_signal = pull_attendance()
        if attendance_signal.get("status") == "ok":
            print(
                f"  Recent {attendance_signal['recent_avg_pct']}% over "
                f"{attendance_signal['recent_games_count']} games  "
                f"({attendance_signal['delta_pct']:+.1f} vs baseline)"
            )
        else:
            print(f"  status: {attendance_signal.get('status')}")
    except Exception as e:
        print(f"  ! attendance pull failed: {e}")
        attendance_signal = {"status": "error", "error": str(e)}

    # 5. Write today's record
    record = {
        "date": today,
        "display_score": display,
        "reactive_score": reactive,
        "baseline_score": baseline,
        "mood_label": mood_label(display),
        "dimensions": dimensions,
        "dimension_confidence": confidence,
        "themes": result.get("themes", []),
        "quotes": result.get("quotes", []),
        "reasoning": result.get("reasoning", ""),
        "source_counts": {
            "reddit_posts": n_posts,
            "reddit_comments": n_comments,
            "match_threads": n_match,
        },
        "hard_signals": {
            "attendance": attendance_signal,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    (DATA_DIR / f"{today}.json").write_text(json.dumps(record, indent=2))
    history.append(record)
    history.sort(key=lambda h: h["date"])
    history_path.write_text(json.dumps(history, indent=2))

    # Summary
    print(f"\n  Display: {display} — {mood_label(display)}")
    print(f"  Reactive: {reactive}  |  Baseline: {baseline}")
    themes = ", ".join(t.get("name", "?") for t in result.get("themes", []))
    print(f"  Themes: {themes}")
    if attendance_signal.get("status") == "ok":
        canary = " 🚨" if attendance_signal.get("canary_signal") else ""
        print(
            f"  Attendance: {attendance_signal['recent_avg_pct']}% "
            f"({attendance_signal['delta_pct']:+.1f} vs baseline){canary}"
        )
    print(f"\n  Wrote data/{today}.json and updated history ({len(history)} days)")

if __name__ == "__main__":
    main()
