#!/usr/bin/env python3
"""
Phan-o-meter v1: Daily Philadelphia Phillies fan sentiment.

Pipeline:
  1. Pull last 24h of posts + comments from r/phillies (prioritize game threads)
  2. Pull recent podcast episodes from Hittin' Season, Phillies Therapy, WIP Daily
     and transcribe with Groq Whisper
  3. Score aggregate mood with Claude across 7 dimensions, with source-aware voice tagging
  4. Pull Citizens Bank Park attendance as independent hard signal
  5. Compute reactive, baseline, and display scores
  6. Write data/YYYY-MM-DD.json and update data/history.json

Usage:
  python phanometer.py               # full run
  python phanometer.py --dry         # skip Claude + transcription (Reddit + attendance only)
  python phanometer.py --no-podcasts # skip podcasts (useful if rate-limited)
  python phanometer.py --no-reddit   # skip Reddit (use from cloud IPs where Reddit 403s)
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
from podcasts import pull_podcasts

# Load .env into environment if present. Keeps `python3 phanometer.py` working
# without needing `export` or `source .env` first. run.sh already handles this
# separately, so this is just belt-and-suspenders for direct invocation.
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

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
SCORING_PROMPT = """You are analyzing Philadelphia Phillies fan sentiment across multiple sources.

You'll receive two kinds of content from the last 24-48 hours:
  1. Reddit posts and comments from r/phillies (tagged [POST], [COMMENT], [MATCH THREAD])
  2. Podcast transcripts from Phillies-focused shows (tagged [PODCAST <voice>: <show>])

Each source has a distinct voice. The left-hand identifier is the INTERNAL KEY
used only in structured JSON fields (voice_breakdown keys). The right-hand side
is the HUMAN LABEL to use in any prose (reasoning, quotes, source_hint, notes).
NEVER write the internal key in prose — always translate to the human label.

  Internal key        Human label         Source
  --------------      -----------         ------
  reddit              r/phillies          raw fan community, sarcastic, reactive, emotional
  fan_analyst         fan analyst         Hittin' Season / Stolnis, Klugh, Roscher
  beat_writer         beat writer         Phillies Therapy / Matt Gelb
  radio_populist      talk-radio host     WIP Daily / Joe Giglio

Weight the PODCAST sources slightly more than individual Reddit comments because hosts
summarize and represent broader fan sentiment. But Reddit match-thread reactions are
the most emotionally real content — weight those heavily when present.

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
  "voice_breakdown": {
    "reddit":           {"score": <int 0-100 or null>, "note": "<1 line, or null if no content>"},
    "fan_analyst":      {"score": <int 0-100 or null>, "note": "<1 line, or null if no content>"},
    "beat_writer":      {"score": <int 0-100 or null>, "note": "<1 line, or null if no content>"},
    "radio_populist":   {"score": <int 0-100 or null>, "note": "<1 line, or null if no content>"}
  },
  "themes": [
    {"name": "<short phrase>", "delta": <int -10 to 10, no leading + on positives>, "sample": "<one-line summary>"}
  ],
  "quotes": [
    {"text": "<quote under 20 words>", "score": <int 0-100>, "source_hint": "<short context, e.g. 'Hittin' Season host' or 'r/phillies game thread'>"}
  ],
  "reasoning": "<2-3 sentences on what's driving today's mood. Note any divergence between the voices, e.g. 'beat writers cautious while fans outraged'.>"
}

Scoring guide:
- 100 = maximum positive fan feeling on that dimension
- 50  = neutral / balanced / mixed
- 0   = maximum negative / despair
- dimension_confidence = how much signal on that dimension did you actually see? 0 = barely mentioned, 100 = heavily discussed
- voice_breakdown = one overall score per voice (null if that voice has no content today)
- health_outlook uses HIGHER = fewer/less-severe injury concerns (inverted from intuitive "anxiety")
- 3-5 themes capturing what fans and shows actually discussed
- 3-4 representative quotes spanning the mood spectrum, drawn from both Reddit and podcasts

Rules:
- Do NOT score individual players (no "Harper: 80", "Bohm: 20"). Focus on dimensions and themes.
- Ignore off-topic content (Eagles, Sixers, random memes, unrelated posts, ads in podcasts)
- Be honest: if the mood is bad, reflect it; don't manufacture optimism
- Podcast ads and sponsor reads should be ignored — they are NOT sentiment signal
- CRITICAL: For voice_breakdown, only score voices that have content in the input below. If a voice is absent from the input (no [PODCAST fan_analyst:...] tag appears, for example), return null for that voice, NOT an inferred score. Never hallucinate a voice's sentiment from context.
- CRITICAL: For quotes, only include text that appears verbatim in the input below. Do not invent or paraphrase quotes.
- CRITICAL: In any prose field (reasoning, quotes[].source_hint, voice_breakdown[*].note, themes[*].sample), NEVER write the internal voice keys (reddit, fan_analyst, beat_writer, radio_populist) verbatim. Always use the human labels from the table above (r/phillies, fan analyst, beat writer, talk-radio host). The underscore keys are machine-only identifiers; user-facing copy must read naturally. For example, write "the beat writer (Phillies Therapy)", not "the beat_writer (Phillies Therapy)".

Content to analyze:
"""

def format_content_for_scoring(reddit_items, podcast_transcripts):
    """Format both Reddit items and podcast transcripts into a single prompt body."""
    lines = []

    # Declare which voices are actually in this payload, to prevent Claude from
    # inferring scores for voices that weren't passed.
    voices_present = set()
    if reddit_items:
        voices_present.add("reddit")
    for pod in podcast_transcripts:
        if pod.get("transcript"):
            voices_present.add(pod.get("voice", "unknown"))

    voices_sorted = sorted(voices_present)
    lines.append(
        "\n=== VOICES PRESENT IN THIS INPUT ===\n"
        f"The following voices have content below: {', '.join(voices_sorted)}.\n"
        "ALL OTHER VOICES must receive null in voice_breakdown.\n"
        "=== END VOICES DECLARATION ===\n"
    )

    # Section 1: Podcast transcripts first (they're the "expert digest" layer)
    for pod in podcast_transcripts:
        if not pod.get("transcript"):
            continue
        header = (
            f'\n=== [PODCAST {pod["voice"]}: {pod["feed_name"]}] '
            f'"{pod["title"]}" ({pod.get("transcript_chars", 0):,} chars) ===\n'
        )
        lines.append(header)
        lines.append(pod["transcript"])
        lines.append("\n=== END PODCAST ===\n")

    # Section 2: Reddit posts + comments, sorted match-threads first then by upvotes
    if reddit_items:
        lines.append("\n=== REDDIT (r/phillies) ===\n")
        items_sorted = sorted(
            reddit_items,
            key=lambda x: (not x.get("is_match_thread", False), -x.get("score", 0)),
        )
        for item in items_sorted:
            if item["kind"] == "post":
                prefix = "[MATCH THREAD POST]" if item.get("is_match_thread") else "[POST]"
                body = f': {item["body"]}' if item["body"] else ""
                lines.append(f'{prefix} ({item["score"]}⬆) "{item["title"]}"{body}')
            else:
                lines.append(
                    f'[COMMENT on "{item["parent_title"][:60]}"] ({item["score"]}⬆): {item["body"]}'
                )

    return "\n".join(lines)

def score_with_claude(reddit_items, podcast_transcripts):
    client = Anthropic()
    content = format_content_for_scoring(reddit_items, podcast_transcripts)
    prompt = SCORING_PROMPT + content

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,  # generous headroom for voice_breakdown + themes + quotes + reasoning
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()

    # Strip code fences defensively even though the prompt forbids them
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:])
        if raw.rstrip().endswith("```"):
            raw = raw.rsplit("```", 1)[0]

    raw = raw.strip()

    # Defensive cleanup: Claude sometimes emits +5 for positive deltas, which is
    # invalid JSON. Strip leading + on numeric values.
    # Matches: `: +5,` or `: +5 ` or `: +5}` or `: +5\n`
    import re
    raw = re.sub(r':\s*\+(\d)', r': \1', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Save the raw response for post-mortem debugging
        debug_path = DATA_DIR / "last_failed_response.txt"
        DATA_DIR.mkdir(exist_ok=True)
        debug_path.write_text(raw)
        print(f"\n  ! Claude response failed to parse as JSON: {e}")
        print(f"  Raw response saved to {debug_path} ({len(raw):,} chars)")
        print(f"  First 500 chars: {raw[:500]}")
        print(f"  Last 500 chars: {raw[-500:]}")
        print(f"  Stop reason: {message.stop_reason}")
        raise

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
    skip_podcasts = "--no-podcasts" in sys.argv
    skip_reddit = "--no-reddit" in sys.argv
    DATA_DIR.mkdir(exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tags = []
    if dry_run:
        tags.append("DRY")
    if skip_reddit:
        tags.append("no reddit")
    if skip_podcasts:
        tags.append("no podcasts")
    tag = f" ({', '.join(tags)})" if tags else ""
    print(f"[{today}] Phan-o-meter daily run{tag}")

    # 1. Pull Reddit (unless explicitly skipped — e.g. from GitHub Actions,
    # where Reddit 403s cloud provider IPs on its public JSON endpoints).
    if skip_reddit:
        print(f"Skipping r/{SUBREDDIT} (--no-reddit).")
        items = []
        n_posts = n_comments = n_match = 0
    else:
        print(f"Pulling r/{SUBREDDIT}...")
        items = pull_reddit()
        n_posts = sum(1 for i in items if i["kind"] == "post")
        n_comments = sum(1 for i in items if i["kind"] == "comment")
        n_match = sum(1 for i in items if i.get("is_match_thread"))
        print(f"  {len(items)} items: {n_posts} posts ({n_match} match threads), {n_comments} comments")

    # 2. Pull podcasts (unless dry-run or explicitly skipped)
    podcasts = []
    if not dry_run and not skip_podcasts:
        try:
            podcasts = pull_podcasts()
        except Exception as e:
            print(f"  ! podcast pull crashed: {e}")
            podcasts = []

    successful_podcasts = [p for p in podcasts if p.get("transcript")]
    total_podcast_chars = sum(p.get("transcript_chars", 0) for p in successful_podcasts)

    if dry_run:
        print("\nDry run — skipping Claude + podcasts. First 3 Reddit items:")
        for item in items[:3]:
            print(f"  - {item}")
        return

    if not items and not successful_podcasts:
        print("  ! No Reddit items and no successful podcasts — nothing to score. Aborting.")
        sys.exit(2)
    if len(items) < 5 and not successful_podcasts:
        print("  ! Very low content volume — results may be unreliable")

    # 3. Score with Claude (Reddit + podcasts together)
    print(f"Scoring with {MODEL}...")
    print(f"  Input: {len(items)} Reddit items + {len(successful_podcasts)} podcast(s), "
          f"{total_podcast_chars:,} podcast chars")
    result = score_with_claude(items, successful_podcasts)

    # 4. Load history and compute composite
    history_path = DATA_DIR / "history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    # Exclude today from history if re-running same day (idempotency)
    history = [h for h in history if h["date"] != today]

    dimensions = result["dimensions"]
    confidence = result["dimension_confidence"]
    reactive = compute_reactive_score(dimensions, confidence)
    baseline = compute_baseline(history)
    # Volume for blending includes podcasts — each successful podcast counts as ~10 reddit items
    volume = len(items) + len(successful_podcasts) * 10
    display = compute_display_score(reactive, baseline, volume)

    # 5. Pull attendance (independent hard signal, not a scoring dimension)
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

    # 6. Write today's record
    record = {
        "date": today,
        "display_score": display,
        "reactive_score": reactive,
        "baseline_score": baseline,
        "mood_label": mood_label(display),
        "dimensions": dimensions,
        "dimension_confidence": confidence,
        "voice_breakdown": result.get("voice_breakdown", {}),
        "themes": result.get("themes", []),
        "quotes": result.get("quotes", []),
        "reasoning": result.get("reasoning", ""),
        "source_counts": {
            "reddit_posts": n_posts,
            "reddit_comments": n_comments,
            "match_threads": n_match,
            "podcasts_attempted": len(podcasts),
            "podcasts_transcribed": len(successful_podcasts),
            "podcast_chars": total_podcast_chars,
        },
        "podcasts_used": [
            {
                "feed_name": p["feed_name"],
                "title": p["title"],
                "voice": p["voice"],
                "chars": p.get("transcript_chars", 0),
            }
            for p in successful_podcasts
        ],
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
    voice_breakdown = result.get("voice_breakdown", {})
    if voice_breakdown:
        voice_summary = []
        for v, data in voice_breakdown.items():
            if data and data.get("score") is not None:
                voice_summary.append(f"{v}:{data['score']}")
        if voice_summary:
            print(f"  Voices: {' | '.join(voice_summary)}")
    if attendance_signal.get("status") == "ok":
        canary = " 🚨" if attendance_signal.get("canary_signal") else ""
        print(
            f"  Attendance: {attendance_signal['recent_avg_pct']}% "
            f"({attendance_signal['delta_pct']:+.1f} vs baseline){canary}"
        )
    print(f"\n  Wrote data/{today}.json and updated history ({len(history)} days)")

if __name__ == "__main__":
    main()
