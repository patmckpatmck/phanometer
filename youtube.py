#!/usr/bin/env python3
"""
Phan-o-meter YouTube module.

Pulls recent short clips from Philadelphia sports-talk YouTube channels
(currently 94WIP only) via the YouTube Data API v3, filters for Phillies-tagged
titles, and pulls auto-captions via youtube-transcript-api (no audio download,
no Whisper).

Returns clip dicts shaped identically to podcasts.py output so both
sources flow into the same scoring pipeline.

Usage:
    python youtube.py              # pull + transcribe last 4 days
    python youtube.py --hours 48   # custom lookback (hours)
    python youtube.py --dry        # list eligible clips, skip captions
    python youtube.py --comments   # pull top-level fan comments (youtube_fan)
"""

# -----------------------------------------------------------------------------
# Known limitation (as of 2026-04-26)
# -----------------------------------------------------------------------------
# Discovery via YouTube Data API v3 works correctly on cloud IPs (uses official
# endpoints with API key auth). Captions fetch via youtube-transcript-api fails
# on GitHub Actions runners with RequestBlocked errors — the library scrapes
# YouTube's frontend rather than using official caption endpoints, and YouTube
# blocks cloud-provider IP ranges at that layer. The previous yt-dlp-based
# approach failed for the same underlying reason.
#
# YouTube's official captions.download endpoint requires OAuth scopes that
# only the video owner can grant, so it's not viable for third-party content.
#
# Planned fix: migrate the daily workflow to a self-hosted runner on a
# residential IP (Mac mini), which sidesteps the IP block class entirely and
# also unblocks Reddit ingestion. Until then, YouTube discovery still runs on
# every workflow execution (cheap, exercises the channel listing path so
# upstream schema changes surface early), captions fail silently per-clip
# with logged errors, and youtube_attempted lands at 0 in the daily JSON.
# -----------------------------------------------------------------------------

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.discovery import build
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# Reuse the keyword list, char cap, and name normalizer from podcasts.py so
# behavior stays consistent across audio sources.
from podcasts import (
    PHILLIES_KEYWORDS,
    TRANSCRIPT_CHAR_CAP,
    normalize_names,
)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

# YouTube channel uploads-playlist convention: every channel has an auto-managed
# uploads playlist whose ID is the channel ID with the "UC" prefix swapped to
# "UU". We use that playlist with playlistItems.list to enumerate the latest
# uploads cheaply (1 quota unit per page, vs. 100 for search.list).
YOUTUBE_CHANNELS = [
    {
        "name": "94WIP",
        "source_tag": "wip_youtube",
        "voice": "radio_populist",
        # channel_id UC9POis6-mA5EInyFiPeVlNQ → uploads UU9POis6-mA5EInyFiPeVlNQ
        "uploads_playlist_id": "UU9POis6-mA5EInyFiPeVlNQ",
        "strategy": "filter",  # Phillies-tagged titles only
    },
]

DEFAULT_LOOKBACK_HOURS = 96          # 4 days
MAX_DURATION_SECONDS = 20 * 60       # skip full-show re-uploads, keep segments
SCAN_LATEST_N = 30                   # how many newest uploads to inspect per channel
YOUTUBE_MAX_CLIPS_PER_RUN = 3        # cost safeguard, newest-first

# --- Comment ingestion (youtube_fan voice) -----------------------------------
# Top-level YouTube comments are a direct-fan-voice source — distinct from the
# caption/transcript track above, which is talk-radio *media* voice and feeds
# radio_populist. Comments feed their own voice: youtube_fan. Do not fold them
# into radio_populist.
#
# This uses the Data API commentThreads.list endpoint (API-key auth, quota-
# metered), NOT the caption scraper. It is therefore NOT subject to the
# youtube-transcript-api / yt-dlp residential-IP block documented above that
# stalls the transcript work — comment ingestion runs fine on GitHub Actions.
#
# Quota math: commentThreads.list costs 1 unit per call, and we make exactly one
# call per video (a single page of up to COMMENTS_PER_VIDEO top-level comments;
# reply threads are skipped for v1). With VIDEOS_FOR_COMMENTS_PER_RUN videos
# that's N units, plus the ~2 units of playlistItems/videos.list discovery. Even
# at the caps below the per-run cost is well under ~10 units against the default
# 10,000-unit daily quota, and the cron runs once per day.
COMMENTS_PER_VIDEO = 20              # top-level comments per video, order=relevance
VIDEOS_FOR_COMMENTS_PER_RUN = 5     # cap videos we pull comments from, newest-first
COMMENT_CHAR_CAP = 400              # per-comment trim (mirrors the reddit comment cap)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _title_matches_phillies(title):
    t = (title or "").lower()
    return any(kw in t for kw in PHILLIES_KEYWORDS)

def _parse_iso8601_duration(s):
    """Parse a YouTube ISO-8601 duration like 'PT12M34S' into seconds.
    Handles H/M/S; returns None on malformed input."""
    if not s or not s.startswith("PT"):
        return None
    h = m = sec = 0
    num = ""
    for ch in s[2:]:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            h = int(num or 0); num = ""
        elif ch == "M":
            m = int(num or 0); num = ""
        elif ch == "S":
            sec = int(num or 0); num = ""
        else:
            return None
    return h * 3600 + m * 60 + sec

def _parse_iso8601_timestamp(s):
    """Parse a YouTube publishedAt like '2026-04-25T14:30:00Z' to aware datetime."""
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None

# -----------------------------------------------------------------------------
# Channel listing (YouTube Data API v3)
# -----------------------------------------------------------------------------
def list_channel_clips(channel, lookback_hours, yt_client):
    """Return clip dicts from a channel within the lookback window, title-filtered
    and duration-capped.

    Two-stage:
      1. playlistItems.list on the uploads playlist → titles + video IDs
         (paginated until SCAN_LATEST_N is reached)
      2. videos.list (batched ≤50 IDs) for authoritative duration + publishedAt
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Stage 1: pull the latest SCAN_LATEST_N uploads via playlistItems.list
    entries = []
    page_token = None
    try:
        while len(entries) < SCAN_LATEST_N:
            req = yt_client.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=channel["uploads_playlist_id"],
                maxResults=min(50, SCAN_LATEST_N - len(entries)),
                pageToken=page_token,
            )
            resp = req.execute()
            for item in resp.get("items", []):
                entries.append({
                    "id": item["contentDetails"]["videoId"],
                    "title": item["snippet"].get("title") or "",
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        print(f"  ! {channel['name']}: playlistItems.list failed ({e})")
        return []

    n_raw = len(entries)

    if n_raw == 0:
        print(f"  ! {channel['name']}: API returned 0 playlist items "
              f"(channel empty or playlist ID wrong)")
        return []

    # Stage 1b: title-only pre-filter (no duration in playlistItems response)
    candidates = []
    n_title_match = 0
    for e in entries:
        if channel["strategy"] == "filter" and not _title_matches_phillies(e["title"]):
            continue
        n_title_match += 1
        candidates.append(e)

    # Stage 2: batched videos.list for duration + publishedAt
    clips = []
    n_dropped_full_dur = 0
    n_dropped_lookback = 0
    n_missing_meta = 0
    if candidates:
        try:
            details = []
            for i in range(0, len(candidates), 50):
                batch_ids = [c["id"] for c in candidates[i:i + 50]]
                req = yt_client.videos().list(
                    part="contentDetails,snippet",
                    id=",".join(batch_ids),
                )
                details.extend(req.execute().get("items", []))
        except Exception as e:
            print(f"  ! {channel['name']}: videos.list failed ({e})")
            return []

        details_by_id = {d["id"]: d for d in details}
        for c in candidates:
            d = details_by_id.get(c["id"])
            if d is None:
                n_missing_meta += 1
                continue
            dur = _parse_iso8601_duration(
                d.get("contentDetails", {}).get("duration")
            )
            pub = _parse_iso8601_timestamp(
                d.get("snippet", {}).get("publishedAt")
            )
            if dur is None or pub is None:
                n_missing_meta += 1
                continue
            if pub < cutoff:
                n_dropped_lookback += 1
                continue
            if dur >= MAX_DURATION_SECONDS:
                n_dropped_full_dur += 1
                continue
            clips.append({
                "feed_name": channel["name"],
                "source_tag": channel["source_tag"],
                "voice": channel["voice"],
                "title": d.get("snippet", {}).get("title") or c["title"],
                "video_id": c["id"],
                "video_url": f"https://www.youtube.com/watch?v={c['id']}",
                "duration_seconds": dur,
                "pub_date": pub.isoformat(),
            })

    print(f"  {channel['name']}: stages — "
          f"raw={n_raw}, title-match={n_title_match}, "
          f"missing-meta={n_missing_meta}, "
          f"dropped-lookback={n_dropped_lookback}, "
          f"dropped-cap={n_dropped_full_dur}")
    return clips

# -----------------------------------------------------------------------------
# Captions
# -----------------------------------------------------------------------------
def fetch_caption_transcript(video_id):
    """Fetch the English auto-captions for a video and return them as a single
    concatenated string. Raises the underlying youtube-transcript-api exception
    on failure so the caller can log a specific marker."""
    fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    return " ".join(snip.text.strip() for snip in fetched if snip.text)

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
def pull_youtube(lookback_hours_override=None, dry=False):
    """Return a list of transcript items from configured YouTube channels.

    Shape matches podcasts.py output so phanometer.py can merge both streams
    into the scoring prompt without special-casing.
    """
    lookback_hours = lookback_hours_override or DEFAULT_LOOKBACK_HOURS
    print(f"Pulling YouTube ({lookback_hours}h lookback)...")

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("  ! YOUTUBE_API_KEY not set — skipping YouTube ingestion")
        return []

    yt_client = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    all_clips = []
    for channel in YOUTUBE_CHANNELS:
        clips = list_channel_clips(channel, lookback_hours, yt_client)
        print(f"  {channel['name']}: {len(clips)} eligible clip(s) "
              f"(<{MAX_DURATION_SECONDS // 60}min, Phillies-tagged)")
        all_clips.extend(clips)

    # Cost safeguard: cap per run, newest first. Keep the cap independent of
    # the podcast cap so a quiet podcast week can't subsidize a noisy YouTube
    # week or vice-versa.
    all_clips.sort(key=lambda c: datetime.fromisoformat(c["pub_date"]), reverse=True)
    if len(all_clips) > YOUTUBE_MAX_CLIPS_PER_RUN:
        dropped = all_clips[YOUTUBE_MAX_CLIPS_PER_RUN:]
        all_clips = all_clips[:YOUTUBE_MAX_CLIPS_PER_RUN]
        print(f"  Cap: keeping newest {YOUTUBE_MAX_CLIPS_PER_RUN}, dropping "
              f"{len(dropped)} older clip(s):")
        for d in dropped:
            print(f"    - [{d['source_tag']}] {d['title'][:60]} ({d['pub_date']})")
    print(f"  After cap: {len(all_clips)} clip(s)")

    if dry:
        print("Dry run — skipping captions fetch")
        return [{**c, "transcript": None} for c in all_clips]

    transcripts = []
    for c in all_clips:
        print(f"  Captions: [{c['source_tag']}] {c['title'][:70]}...")
        try:
            text = fetch_caption_transcript(c["video_id"])
        except TranscriptsDisabled:
            print(f"    ! captions disabled for {c['video_id']}")
            transcripts.append({**c, "transcript": None, "error": "transcripts_disabled"})
            continue
        except NoTranscriptFound:
            print(f"    ! no English transcript for {c['video_id']}")
            transcripts.append({**c, "transcript": None, "error": "no_transcript_found"})
            continue
        except VideoUnavailable:
            print(f"    ! video unavailable: {c['video_id']}")
            transcripts.append({**c, "transcript": None, "error": "video_unavailable"})
            continue
        except Exception as e:
            print(f"    ! captions fetch failed: {e}")
            transcripts.append({**c, "transcript": None, "error": str(e)})
            continue

        text = normalize_names(text)
        if len(text) > TRANSCRIPT_CHAR_CAP:
            text = text[:TRANSCRIPT_CHAR_CAP] + "...[truncated]"
        transcripts.append({
            **c,
            "transcript": text,
            "transcript_chars": len(text),
        })
        print(f"    ✓ {len(text):,} chars from captions")

    return transcripts

# -----------------------------------------------------------------------------
# Comments (youtube_fan voice)
# -----------------------------------------------------------------------------
def pull_youtube_comments(lookback_hours_override=None):
    """Return top-level fan comments from recent channel videos, tagged to the
    youtube_fan voice.

    Self-contained: it re-resolves the eligible videos in the lookback window
    via the same channel-listing path the caption track uses (cheap — a couple
    of quota units, see the quota note on the config constants), then pulls one
    page of top-level comments per video. Keeping it independent of pull_youtube
    means comments still flow even though captions are IP-blocked on CI; the
    duplicate discovery cost is negligible. Reply threads are skipped for v1.

    Comment item shape is intentionally distinct from the caption clip shape so
    phanometer.py can route it into its own scoring section.
    """
    lookback_hours = lookback_hours_override or DEFAULT_LOOKBACK_HOURS
    print(f"Pulling YouTube comments ({lookback_hours}h lookback)...")

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("  ! YOUTUBE_API_KEY not set — skipping YouTube comment ingestion")
        return []

    yt_client = build("youtube", "v3", developerKey=api_key, cache_discovery=False)

    # Resolve eligible videos in the window (Phillies-tagged, duration-capped),
    # newest-first, then cap how many we pull comments from.
    videos = []
    for channel in YOUTUBE_CHANNELS:
        videos.extend(list_channel_clips(channel, lookback_hours, yt_client))
    videos.sort(key=lambda c: datetime.fromisoformat(c["pub_date"]), reverse=True)
    if len(videos) > VIDEOS_FOR_COMMENTS_PER_RUN:
        print(f"  Comment cap: pulling from newest {VIDEOS_FOR_COMMENTS_PER_RUN} "
              f"of {len(videos)} eligible video(s)")
        videos = videos[:VIDEOS_FOR_COMMENTS_PER_RUN]

    comments = []
    for v in videos:
        try:
            resp = yt_client.commentThreads().list(
                part="snippet",
                videoId=v["video_id"],
                maxResults=COMMENTS_PER_VIDEO,
                order="relevance",
                textFormat="plainText",
            ).execute()
        except Exception as e:
            # Comments disabled (403 commentsDisabled) or other per-video error —
            # skip this video and keep going, same posture as the caption track.
            print(f"  ! comments unavailable for {v['video_id']} ({e})")
            continue

        n_kept = 0
        for item in resp.get("items", []):
            snip = item["snippet"]["topLevelComment"]["snippet"]
            text = (snip.get("textOriginal") or snip.get("textDisplay") or "").strip()
            if len(text) < 10:
                continue
            comments.append({
                "kind": "youtube_comment",
                "voice": "youtube_fan",
                "feed_name": v["feed_name"],
                "video_title": v["title"],
                "video_id": v["video_id"],
                "text": text[:COMMENT_CHAR_CAP],
                "likes": snip.get("likeCount", 0),
                "published_at": snip.get("publishedAt"),
            })
            n_kept += 1
        print(f"  [{v['feed_name']}] {n_kept} comment(s) from \"{v['title'][:50]}\"")

    print(f"  Total: {len(comments)} YouTube comment(s)")
    return comments

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    dry = "--dry" in sys.argv
    override = None
    if "--hours" in sys.argv:
        i = sys.argv.index("--hours")
        override = int(sys.argv[i + 1])

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    if "--comments" in sys.argv:
        comments = pull_youtube_comments(lookback_hours_override=override)
        print(f"\n{len(comments)} comment(s):")
        for c in comments:
            print(f"  [{c['feed_name']}] ({c['likes']}👍) {c['text'][:80]}")
    else:
        results = pull_youtube(lookback_hours_override=override, dry=dry)
        print(f"\n{len(results)} clip(s):")
        for r in results:
            status = "dry" if r.get("transcript") is None and "error" not in r else \
                     ("error: " + r["error"]) if "error" in r else \
                     f"{r.get('transcript_chars', 0):,} chars"
            print(f"  [{r['source_tag']}] {r['title'][:60]} — {status}")
