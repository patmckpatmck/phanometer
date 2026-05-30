#!/usr/bin/env python3
"""
Phan-o-meter v1: Daily Philadelphia Phillies fan sentiment.

Pipeline:
  1. Pull last 24h of posts + comments from r/phillies (prioritize game threads)
  2. Pull recent podcast episodes from Hittin' Season, Phillies Therapy, WIP Daily
     and transcribe with Groq Whisper
  3. Score aggregate mood with Claude across 7 dimensions, with source-aware voice tagging
  4. Pull Citizens Bank Park attendance as independent hard signal
  5. Compute the reactive score (the display score) and a 30-day EWMA baseline
     as context for the delta badge and trend chart. Flag the day as
     insufficient_signal when total content volume falls below threshold.
  6. Write data/YYYY-MM-DD.json and update data/history.json

Usage:
  python phanometer.py               # full run
  python phanometer.py --dry         # skip Claude + transcription (Reddit + attendance only)
  python phanometer.py --no-podcasts # skip podcasts (useful if rate-limited)
  python phanometer.py --no-youtube  # skip 94WIP YouTube clips
  python phanometer.py --no-reddit   # skip Reddit (e.g. when OAuth creds are unavailable)
"""

import os
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import praw
from anthropic import Anthropic

from attendance import pull_attendance, get_team_facts
from podcasts import pull_podcasts
from youtube import pull_youtube, pull_youtube_comments

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

# Content-volume gate for publishing a display score. The metric is:
#   reddit_items + (audio_chars / CHARS_PER_AUDIO_MINUTE)
# where audio_chars covers podcast + YouTube transcripts. A single ~30-minute
# podcast episode clears the threshold on its own; a day with no audio and a
# handful of Reddit posts does not. Tune here.
# TODO: revisit after ~1 month of data covering weekday/weekend, home/road,
# and in/out-of-season patterns. The initial 30 is a v1 guess calibrated so a
# single off-day podcast clears it — real-world distribution may want it
# tuned up (fewer "insufficient" days, higher quality bar) or down.
MIN_CONTENT_VOLUME = 30
CHARS_PER_AUDIO_MINUTE = 750  # ~150 words/min × ~5 chars/word

# Philly-voice mood taxonomy
MOOD_TIERS = [
    (90, "Red October"),
    (80, "Rally Towel"),
    (70, "Buzzing"),
    (60, "High Hopes"),
    (50, "Touch and Go"),
    (40, "Uneasy"),
    (30, "Oh No"),
    (20, "Not Again"),
    (10, "Meltdown"),
    (0,  "Rock Bottom"),
]

def mood_label(score):
    for threshold, label in MOOD_TIERS:
        if score >= threshold:
            return label
    return "Rock Bottom"

# -----------------------------------------------------------------------------
# Reddit pull (authenticated read-only via PRAW / OAuth)
# -----------------------------------------------------------------------------
# History: this used to hit Reddit's public www.reddit.com/*.json endpoints with
# raw urllib and no auth. As of 2026, Reddit returns 403 to unauthenticated
# requests against those endpoints. The root cause was the application-layer auth
# wall, NOT the runner's IP — a residential IP gets the same 403. The durable fix
# is OAuth: a read-only "script" app on the free Data API tier (non-commercial,
# 100 QPM), which needs no payment. See README "Setup" for app registration.
MATCH_THREAD_KEYWORDS = ["game thread", "post game", "postgame", "pre game", "pregame"]
# Reddit asks for a unique, descriptive User-Agent identifying the app and its
# operator. REDDIT_USERNAME is only used to fill the "by u/<name>" suffix.
USER_AGENT = f"phanometer/1.0 by u/{os.environ.get('REDDIT_USERNAME', 'unknown')}"

def is_match_thread(title):
    t = title.lower()
    return any(kw in t for kw in MATCH_THREAD_KEYWORDS)

def _reddit_client():
    """Build a read-only PRAW client from REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET.

    With no username/password/refresh token supplied, PRAW authenticates via the
    client-credentials grant and the resulting instance is read-only — all we need
    for pulling public subreddit content.
    """
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set — register a "
            "read-only 'script' app at https://www.reddit.com/prefs/apps and "
            "add the credentials to .env (see README Setup)."
        )
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=USER_AGENT,
    )

def pull_reddit():
    cutoff = time.time() - LOOKBACK_HOURS * 3600
    items = []

    reddit = _reddit_client()
    subreddit = reddit.subreddit(SUBREDDIT)

    # 1. Get the newest posts from the subreddit
    for post in subreddit.new(limit=MAX_POSTS):
        if (post.created_utc or 0) < cutoff:
            continue

        title = post.title
        match = is_match_thread(title)
        items.append({
            "kind": "post",
            "title": title,
            "body": (post.selftext or "")[:500],
            "score": post.score or 0,
            "created_utc": post.created_utc,
            "is_match_thread": match,
        })

        # 2. Pull top comments for each post. Match threads get a bigger budget.
        cap = MATCH_THREAD_COMMENT_CAP if match else REGULAR_POST_COMMENT_CAP
        try:
            post.comment_sort = "top"
            post.comment_limit = cap
            # Drop "load more comments" placeholders so iteration yields real
            # comments only; we keep just the top-level ones (no recursion), same
            # as the old listing-based fetch.
            post.comments.replace_more(limit=0)
            for c in post.comments[:cap]:
                body = (c.body or "").strip()
                if not body or body in ("[deleted]", "[removed]") or len(body) < 10:
                    continue
                if (c.created_utc or 0) < cutoff:
                    continue
                items.append({
                    "kind": "comment",
                    "parent_title": title,
                    "body": body[:400],
                    "score": c.score or 0,
                    "created_utc": c.created_utc,
                })
        except Exception as e:
            print(f"  ! error fetching comments for '{title[:40]}': {e}")

    return items

# -----------------------------------------------------------------------------
# Scoring with Claude
# -----------------------------------------------------------------------------
# postseason_belief: calibrated April 2026 to stop coping framing (wild-card-era
# reassurance, "it's only April," recovery precedents from other teams' slow
# starts) from raising the score. Revisit if postseason_belief fails to rise
# during a genuine hot streak or a positive trade-deadline signal.
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
  youtube_fan         YouTube commenters  raw fan voice from video comment sections, reactive, unfiltered

Weight the PODCAST sources slightly more than individual Reddit or YouTube comments
because hosts summarize and represent broader fan sentiment. But Reddit match-thread
reactions are the most emotionally real content — weight those heavily when present.

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
    "radio_populist":   {"score": <int 0-100 or null>, "note": "<1 line, or null if no content>"},
    "youtube_fan":      {"score": <int 0-100 or null>, "note": "<1 line, or null if no content>"}
  },
  "themes": [
    {"name": "<short phrase>", "delta": <int -10 to 10, no leading + on positives>, "sample": "<one-line summary>"}
  ],
  "quotes": [
    {"text": "<quote under 20 words>", "score": <int 0-100>, "source_hint": "<short context, e.g. 'Hittin' Season host' or 'r/phillies game thread'>"}
  ],
  "vibe_summary": "<ONE sentence, max 25 words, describing how Phillies fans feel today. Plain prose suitable for display under a 'How Philly feels about the Phillies, today' header. Do NOT start with a number or statistic. Do NOT include decimal figures (e.g. ERA, batting averages). Write it as a standalone sentence that reads naturally on its own. If a RECENT VIBE SUMMARIES block appears below the input, do not echo its sentence structure, opening, or framing.>",
  "reasoning": "<2-3 sentences on what's driving today's mood. Note any divergence between the voices, e.g. 'beat writers cautious while fans outraged'.>",
  "people_mentioned": ["Thomson", "Mattingly", "Dombrowski", "Luzardo", "Stott"]
  }

Scoring guide:
- 100 = maximum positive fan feeling on that dimension
- 50  = neutral / balanced / mixed
- 0   = maximum negative / despair
- dimension_confidence = how much signal on that dimension did you actually see? 0 = barely mentioned, 100 = heavily discussed
- voice_breakdown = one overall score per voice (null if that voice has no content today)
- health_outlook uses HIGHER = fewer/less-severe injury concerns (inverted from intuitive "anxiety")
- postseason_belief has its own definition — see "postseason_belief scoring" below. Read before scoring this dimension.
- 3-5 themes capturing what fans and shows actually discussed
- 3-4 representative quotes spanning the mood spectrum, drawn from both Reddit and podcasts

postseason_belief scoring:
This dimension measures EXPRESSED BELIEF that the Phillies will make a deep playoff run THIS season. It is NOT a resilience or "don't panic" index.

RAISES postseason_belief:
- Expressed confidence in the roster's playoff trajectory ("this team can win the division," "still the deepest roster in the NL East," "best rotation in baseball when healthy")
- Discussion of the Phillies as trade-deadline BUYERS, or expectations the front office will add at the deadline
- Playoff-odds discussion framed positively (PECOTA/FanGraphs percentages cited approvingly, confident NLCS/World Series predictions)
- Arguments that the current roster, as constructed, is built to make a deep October run

DOES NOT raise postseason_belief — this is COPING FRAMING, not belief:
- Invoking the wild-card era to argue panic is premature ("three wild cards means no one's out in April")
- Citing recovery precedents from other teams' slow starts ("the 2019 Nationals were 19-31 and won the World Series")
- "It's only April" / "long season" / "162 is a lot of games" framing
- Analysts explicitly managing fan despair, reassuring listeners not to overreact, or talking callers off a ledge
- Generic structural reassurance that panic is premature

Coping framing is a REBUTTAL to despair, not an EXPRESSION of belief. When the only postseason-adjacent content is analysts telling fans to stay calm, postseason_belief should stay LOW (tracking the rest of the day's negativity), not rise.

Examples:
- CORRECT read, belief rising (score ~65+): Hosts spend a segment discussing the Phillies as clear deadline buyers, defending the roster's ceiling, or confidently projecting a deep October run.
- CORRECT read, belief LOW during a losing streak even with coping framing present (score ~15-25): "It's only April, the wild-card era forgives slow starts, teams have come back from 8-15 before." This is structural reassurance, not expressed belief — keep postseason_belief low, in line with the rest of the day's sentiment.

people_mentioned:
List Phillies players, coaches, front-office figures, broadcasters, and other team-affiliated people who were substantively discussed in the day's content.
- Use the standard short form: last name only when unambiguous (e.g., "Bohm", "Harper", "Wheeler"); full name when needed for clarity (e.g., "Aidan Miller" not "Miller" if there is another Miller; "Rob Thomson" since "Thomson" alone is also reasonable).
- Exclude: people mentioned only in passing without sentiment attached (e.g., a name dropped once in a stat line); opposing players unless they are a recurring storyline; generic references like "the manager" or "the rotation".
- Order: roughly by prominence in the day's discussion — most-discussed first.
- Use canonical Phillies-name spellings consistent with how transcripts are normalized (e.g., "Rob Thomson" not "Thompson", "Taijuan Walker" not "Tywan Walker"), so the field stays consistent across days.
Example: "people_mentioned": ["Thomson", "Mattingly", "Dombrowski", "Luzardo", "Stott"]

Voice/source attribution — strict field-level rules:

The output schema has two kinds of text fields. Different rules apply.

METADATA fields (attribution is the purpose of the field — use human labels here when natural):
- voice_breakdown[*].note      — body text for each voice's per-voice section
- quotes[].source_hint         — attribution label rendered above each quote

NARRATIVE PROSE fields (attribution is FORBIDDEN — the UI renders attribution separately around these fields, so mentioning sources in the prose itself is redundant and weakens the writing):
- reasoning                    — renders as "The Vibe" summary
- themes[].name                — renders as Cheers & Groans headline
- themes[].sample              — renders as Cheers & Groans body copy
- quotes[].text                — renders as the In the Air blurb body (must still be verbatim from input; see below)

HARD RULE for every narrative-prose field:
Do NOT reference sources, shows, hosts, podcasts, callers, Reddit, YouTube, comment sections, "voices," or any meta-language about who is saying something. Write about the SUBSTANCE only — what is happening with the team, not who is discussing it.

Violations — these phrases and any close variants are FORBIDDEN in narrative prose fields:
- "both shows", "both podcasts", "both shows agree", "the shows agree"
- "fan hosts", "the hosts", "podcast hosts", "hosts say", "hosts describe"
- "callers", "callers agree", "callers say"
- "the podcast voices", "both podcast voices", "across both present voices", "across both voices"
- the bare word "voices" used as a noun meaning sources (e.g., "voices sympathetic to X," "voices on the left," "even voices that...") — this is the single most common leak, treat it as banned
- "sentiment across sources", "sentiment across voices", "sentiment across both podcast voices"
- "fan analyst", "talk-radio host", "beat writer" as subjects of a sentence in narrative prose
- "according to the fan analyst", "per the beat writer"
- "Reddit", "r/phillies" as a subject (e.g., "Reddit is outraged")
- "YouTube", "YouTube commenters", "the comments", "commenters" as a subject (e.g., "YouTube commenters are furious")
- any other formulation that names WHERE the sentiment is coming from

Correct (substance only):
  "The eight-game losing streak and -50 run differential have pushed fan mood to near rock-bottom."
Incorrect (attribution leak):
  "Sentiment across both podcast voices is near rock-bottom, driven by an eight-game losing streak."

Correct:
  "Historically bad offensive production — 0-for-26 with RISP over six games."
Incorrect:
  "Both shows describe the offensive production as historically bad."

Expressing tone divergence WITHOUT naming sources:
The most tempting leak is a sentence like "one voice contextualizes while the other alarms." DO NOT write that. If divergence matters, describe the SUBSTANCE of the two positions directly, without attributing them:
Correct (substance-only divergence):
  "The mood is split between contextualizing framings — wild-card-era reassurance, historical comeback precedents — and unambiguous alarm that is openly forecasting managerial dismissal."
Incorrect (attribution leak via "voices"):
  "One voice contextualizes while the other has moved into unambiguous alarm."
Incorrect (attribution leak via "voices sympathetic to"):
  "Even voices sympathetic to the manager acknowledge he may pay the price."
Correct rewrite of the above:
  "Even sympathetic analysis concedes the manager may pay the price for a roster problem not of his making."

For quotes[].text specifically: the quote must appear verbatim in the input. Prefer verbatim quotes about the team, players, or front office. If the only verbatim candidate is meta-commentary about other media ("both shows agree," "fan hosts say"), pick a different verbatim candidate instead.

SELF-CHECK — MANDATORY before emitting JSON:
Re-read each narrative-prose field below and confirm no sentence references sources, shows, hosts, callers, voices, Reddit, YouTube, comment sections, or where a sentiment is coming from:
  - reasoning
  - every themes[].name
  - every themes[].sample
  - every quotes[].text
If any do, rewrite them to describe substance only. Do not emit the JSON until every narrative sentence passes this check.

Rules:
- Do NOT score individual players (no "Harper: 80", "Bohm: 20"). Focus on dimensions and themes.
- Ignore off-topic content (Eagles, Sixers, random memes, unrelated posts, ads in podcasts)
- Be honest: if the mood is bad, reflect it; don't manufacture optimism
- Podcast ads and sponsor reads should be ignored — they are NOT sentiment signal
- CRITICAL: For voice_breakdown, only score voices that have content in the input below. If a voice is absent from the input (no [PODCAST fan_analyst:...] tag appears, for example), return null for that voice, NOT an inferred score. Never hallucinate a voice's sentiment from context.
- CRITICAL: For quotes, only include text that appears verbatim in the input below. Do not invent or paraphrase quotes.
- CRITICAL: In the METADATA fields where attribution is expected (voice_breakdown[*].note, quotes[].source_hint), NEVER write the internal voice keys (reddit, fan_analyst, beat_writer, radio_populist, youtube_fan) verbatim. Use the human labels from the table above (r/phillies, fan analyst, beat writer, talk-radio host, YouTube commenters). Example: write "the beat writer (Phillies Therapy)", not "the beat_writer (Phillies Therapy)".

GROUND-TRUTH FACTS:
The "Content to analyze" section may begin with a "GROUND TRUTH (authoritative...)" block listing the team's current record, streak, and division position as of pipeline run time. When this block is present:
- Treat these values as authoritative.
- Any references in your output to record, streak, or division position MUST use these values, not numbers mentioned in podcast content.
- Podcast content reflects the moment a host recorded — often a day or more before this run — and may be outdated. Use podcast content for tone, framing, and qualitative claims; use ground truth for current numerical state.

Content to analyze:
"""

def format_content_for_scoring(reddit_items, podcast_transcripts, team_facts=None,
                               youtube_comments=None):
    """Format Reddit items, podcast transcripts, and YouTube fan comments into a
    single prompt body. If team_facts has all three fields populated, prepend a
    GROUND TRUTH block."""
    lines = []
    youtube_comments = youtube_comments or []

    if team_facts and all(team_facts.get(k) is not None for k in ("record", "streak", "games_behind")):
        lines.append(
            "\nGROUND TRUTH (authoritative, as of pipeline run time):\n"
            f"- Record: {team_facts['record']}\n"
            f"- Current streak: {team_facts['streak']}\n"
            f"- Games back in division: {team_facts['games_behind']}\n"
        )

    # Declare which voices are actually in this payload, to prevent Claude from
    # inferring scores for voices that weren't passed.
    voices_present = set()
    if reddit_items:
        voices_present.add("reddit")
    if youtube_comments:
        voices_present.add("youtube_fan")
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

    # Section 3: YouTube fan comments (youtube_fan voice). Raw, unfiltered fan
    # reactions — kept distinct from the caption/transcript track, which is
    # talk-radio media voice. Sorted by likes so the loudest comments lead.
    if youtube_comments:
        lines.append("\n=== YOUTUBE FAN COMMENTS ===\n")
        for c in sorted(youtube_comments, key=lambda x: -x.get("likes", 0)):
            lines.append(
                f'[COMMENT on "{c["video_title"][:60]}"] ({c.get("likes", 0)}👍): {c["text"]}'
            )

    return "\n".join(lines)

def recent_vibe_summaries(history, n=3):
    """Return up to the last n non-empty vibe summaries as (date, summary)
    pairs, oldest-first. Fed into the scoring prompt so vibe_summary doesn't
    collapse into the same sentence frame on days when the dominant storyline
    is unchanged. Empty summaries (e.g. insufficient-signal days) are skipped."""
    out = []
    for h in reversed(history):
        vs = (h.get("vibe_summary") or "").strip()
        if vs:
            out.append((h["date"], vs))
        if len(out) >= n:
            break
    return list(reversed(out))


def format_recent_vibes_block(recent_vibes):
    """Render recent vibe summaries plus an anti-repetition instruction.
    Scoped to the wording of vibe_summary ONLY — it must not change dimension
    scores, and it must not pressure Claude to invent a change the content
    doesn't support."""
    if not recent_vibes:
        return ""
    lines = ["\n\n=== RECENT VIBE SUMMARIES (most recent last) ==="]
    for date, vs in recent_vibes:
        lines.append(f"- {date}: {vs}")
    lines.append("=== END RECENT VIBE SUMMARIES ===")
    lines.append(
        "Your vibe_summary must NOT reuse the sentence structure, opening, or "
        "framing of the recent summaries above. Find a fresh angle. If today's "
        "dominant storyline is genuinely unchanged from those days, foreground a "
        "different thread from today's content rather than restating the same "
        "frame. Do NOT manufacture a change the content doesn't support, and do "
        "NOT let this instruction alter your dimension scores — it governs the "
        "wording of vibe_summary only.\n"
    )
    return "\n".join(lines)


def score_with_claude(reddit_items, podcast_transcripts, team_facts=None, recent_vibes=None,
                      youtube_comments=None):
    client = Anthropic()
    content = format_content_for_scoring(
        reddit_items, podcast_transcripts, team_facts, youtube_comments=youtube_comments
    )
    prompt = SCORING_PROMPT + content + format_recent_vibes_block(recent_vibes)

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

def compute_content_volume(text_item_count, audio_chars):
    """Discrete text items + transcribed audio minutes. Used for the
    insufficient-signal gate.

    Decision: YouTube fan comments count as discrete text items (like Reddit
    posts/comments), so they join the text-item tally — NOT the audio-minutes
    side. A comment is one short fan utterance, the same unit a Reddit item is;
    it carries no playback duration, so converting it to "minutes" would be
    meaningless. Callers pass len(reddit_items) + len(youtube_comments) here."""
    audio_minutes = audio_chars / CHARS_PER_AUDIO_MINUTE
    return round(text_item_count + audio_minutes)

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    dry_run = "--dry" in sys.argv
    skip_podcasts = "--no-podcasts" in sys.argv
    skip_youtube = "--no-youtube" in sys.argv
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
    if skip_youtube:
        tags.append("no youtube")
    tag = f" ({', '.join(tags)})" if tags else ""
    print(f"[{today}] Phan-o-meter daily run{tag}")

    # 1. Pull Reddit (unless explicitly skipped). Note: --no-reddit was added
    # back when GitHub Actions runs 403'd; the real cause was the unauthenticated
    # auth wall, now fixed by OAuth (see pull_reddit), not the runner's IP.
    if skip_reddit:
        print(f"Skipping r/{SUBREDDIT} (--no-reddit).")
        items = []
        n_posts = n_comments = n_match = 0
    else:
        print(f"Pulling r/{SUBREDDIT}...")
        try:
            items = pull_reddit()
        except Exception as e:
            print(f"  ! reddit pull crashed: {e}")
            items = []
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

    # 2b. Pull 94WIP YouTube clips — separate source, same transcript shape
    # so the scoring prompt treats podcasts + clips as one audio stream.
    youtube_clips = []
    if not dry_run and not skip_youtube:
        try:
            youtube_clips = pull_youtube()
        except Exception as e:
            print(f"  ! youtube pull crashed: {e}")
            youtube_clips = []

    # 2b-ii. Pull YouTube fan comments — a direct-fan-voice source (youtube_fan),
    # distinct from the caption track above. This is a Data API call, not the
    # caption scraper, so it is unaffected by the transcript IP block.
    youtube_comments = []
    if not dry_run and not skip_youtube:
        try:
            youtube_comments = pull_youtube_comments()
        except Exception as e:
            print(f"  ! youtube comment pull crashed: {e}")
            youtube_comments = []

    successful_podcasts_only = [p for p in podcasts if p.get("transcript")]
    successful_youtube = [y for y in youtube_clips if y.get("transcript")]
    successful_podcasts = successful_podcasts_only + successful_youtube
    total_audio_chars = sum(p.get("transcript_chars", 0) for p in successful_podcasts)

    if dry_run:
        print("\nDry run — skipping Claude + podcasts. First 3 Reddit items:")
        for item in items[:3]:
            print(f"  - {item}")
        return

    if not items and not successful_podcasts and not youtube_comments:
        print("  ! No Reddit items, audio transcripts, or YouTube comments — "
              "nothing to score. Aborting.")
        sys.exit(2)
    if len(items) + len(youtube_comments) < 5 and not successful_podcasts:
        print("  ! Very low content volume — results may be unreliable")

    # 2c. Pull ground-truth team facts (record, streak, GB) so the scoring
    # prompt can override stale numbers from podcast content. All-None on
    # API failure — pipeline still runs sentiment-only.
    print("Pulling team facts from MLB Stats API...")
    team_facts = get_team_facts()
    if any(v is not None for v in team_facts.values()):
        print(f"  Record {team_facts['record']}, streak {team_facts['streak']}, "
              f"GB {team_facts['games_behind']}")
    else:
        print("  ! team facts unavailable — prompt will omit ground-truth block")

    # Load history before scoring so recent vibe summaries can be fed into the
    # prompt (anti-repetition for vibe_summary). Exclude today for idempotency
    # on same-day re-runs.
    history_path = DATA_DIR / "history.json"
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    history = [h for h in history if h["date"] != today]

    # 3. Score with Claude (Reddit + podcasts + youtube captions as audio,
    # YouTube comments as the youtube_fan voice)
    print(f"Scoring with {MODEL}...")
    print(f"  Input: {len(items)} Reddit items + {len(successful_podcasts_only)} podcast(s) "
          f"+ {len(successful_youtube)} YouTube clip(s) + {len(youtube_comments)} YouTube "
          f"comment(s), {total_audio_chars:,} audio chars")
    result = score_with_claude(
        items, successful_podcasts, team_facts,
        recent_vibes=recent_vibe_summaries(history),
        youtube_comments=youtube_comments,
    )

    # 4. Compute composite
    dimensions = result["dimensions"]
    confidence = result["dimension_confidence"]
    reactive = compute_reactive_score(dimensions, confidence)
    baseline = compute_baseline(history)

    content_volume = compute_content_volume(len(items) + len(youtube_comments), total_audio_chars)
    insufficient_signal = content_volume < MIN_CONTENT_VOLUME
    display = None if insufficient_signal else reactive
    display_mood = mood_label(display) if display is not None else None

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
        "insufficient_signal": insufficient_signal,
        "content_volume": content_volume,
        "mood_label": display_mood,
        "dimensions": dimensions,
        "dimension_confidence": confidence,
        "voice_breakdown": result.get("voice_breakdown", {}),
        "themes": result.get("themes", []),
        "quotes": result.get("quotes", []),
        "vibe_summary": result.get("vibe_summary", ""),
        "reasoning": result.get("reasoning", ""),
        "people_mentioned": result.get("people_mentioned", []),
        "source_counts": {
            "reddit_posts": n_posts,
            "reddit_comments": n_comments,
            "match_threads": n_match,
            "podcasts_attempted": len(podcasts),
            "podcasts_transcribed": len(successful_podcasts_only),
            "podcast_chars": sum(
                p.get("transcript_chars", 0) for p in successful_podcasts_only
            ),
            "youtube_attempted": len(youtube_clips),
            "youtube_transcribed": len(successful_youtube),
            "youtube_chars": sum(
                y.get("transcript_chars", 0) for y in successful_youtube
            ),
            "youtube_comments": len(youtube_comments),
            "youtube_comment_chars": sum(
                len(c.get("text", "")) for c in youtube_comments
            ),
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
        "team_facts": team_facts,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    (DATA_DIR / f"{today}.json").write_text(json.dumps(record, indent=2))
    history.append(record)
    history.sort(key=lambda h: h["date"])
    history_path.write_text(json.dumps(history, indent=2))

    # Summary
    if insufficient_signal:
        print(f"\n  Display: — (insufficient signal, volume={content_volume} < {MIN_CONTENT_VOLUME})")
    else:
        print(f"\n  Display: {display} — {display_mood}")
    print(f"  Reactive: {reactive}  |  Baseline: {baseline}  |  Volume: {content_volume}")
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
