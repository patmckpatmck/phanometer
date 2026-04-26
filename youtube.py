#!/usr/bin/env python3
"""
Phan-o-meter YouTube module.

Pulls recent short clips from Philadelphia sports-talk YouTube channels
(currently 94WIP only) via yt-dlp, filters for Phillies-tagged titles,
downloads audio, and transcribes with OpenAI Whisper.

Returns clip dicts shaped identically to podcasts.py output so both
sources flow into the same scoring pipeline.

Usage:
    python youtube.py              # pull + transcribe last 4 days
    python youtube.py --hours 48   # custom lookback (hours)
    python youtube.py --dry        # list eligible clips, skip transcription
"""

import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yt_dlp import YoutubeDL

# Reuse the keyword list and Whisper pipeline from podcasts.py so behavior
# stays consistent and there's one source of truth for both.
from podcasts import (
    PHILLIES_KEYWORDS,
    TRANSCRIPT_CHAR_CAP,
    MAX_UPLOAD_BYTES,
    compress_for_transcription,
    normalize_names,
    transcribe_audio,
)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

YOUTUBE_CHANNELS = [
    {
        "name": "94WIP",
        "source_tag": "wip_youtube",
        "voice": "radio_populist",
        # channel_id: UC9POis6-mA5EInyFiPeVlNQ. We go via the handle URL
        # because YouTube's public RSS endpoint (feeds/videos.xml) was
        # returning 404 as of 2026-04. yt-dlp resolves the channel directly.
        "channel_url": "https://www.youtube.com/@SportsRadio94WIP/videos",
        "strategy": "filter",  # Phillies-tagged titles only
    },
]

DEFAULT_LOOKBACK_HOURS = 96          # 4 days
MAX_DURATION_SECONDS = 20 * 60       # skip full-show re-uploads, keep segments
SCAN_LATEST_N = 30                   # how many newest uploads to inspect per channel
YOUTUBE_MAX_CLIPS_PER_RUN = 3        # cost safeguard, newest-first

# -----------------------------------------------------------------------------
# Channel listing
# -----------------------------------------------------------------------------
def _title_matches_phillies(title):
    t = (title or "").lower()
    return any(kw in t for kw in PHILLIES_KEYWORDS)

def list_channel_clips(channel, lookback_hours):
    """Return clip dicts from a channel within the lookback window, title-filtered
    and duration-capped.

    Two-pass:
      1. Flat playlist listing (one yt-dlp call, no per-video fetches)
      2. Full metadata fetch only for survivors — we need the authoritative
         upload timestamp, which the flat listing usually omits
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    flat_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlistend": SCAN_LATEST_N,
    }
    try:
        with YoutubeDL(flat_opts) as ydl:
            info = ydl.extract_info(channel["channel_url"], download=False)
    except Exception as e:
        print(f"  ! {channel['name']}: channel listing failed ({e})")
        return []

    entries = info.get("entries") or []
    n_raw = len(entries)

    if n_raw == 0:
        print(f"  ! {channel['name']}: yt-dlp returned 0 entries "
              f"(possible bot-detection)")
        return []

    # Pre-filter on shallow metadata (title + duration when present)
    candidates = []
    n_title_match = 0
    for e in entries:
        title = e.get("title") or ""
        if channel["strategy"] == "filter" and not _title_matches_phillies(title):
            continue
        n_title_match += 1
        shallow_dur = e.get("duration")
        if shallow_dur is not None and shallow_dur >= MAX_DURATION_SECONDS:
            continue
        candidates.append({"video_id": e["id"], "title": title})
    n_shallow_dur_ok = len(candidates)

    full_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    clips = []
    n_missing_meta = 0
    n_dropped_lookback = 0
    n_dropped_full_dur = 0
    with YoutubeDL(full_opts) as ydl:
        for c in candidates:
            url = f"https://www.youtube.com/watch?v={c['video_id']}"
            try:
                inf = ydl.extract_info(url, download=False)
            except Exception as ex:
                print(f"  ! {channel['name']}: metadata fetch failed for "
                      f"{c['video_id']} ({ex})")
                continue
            ts = inf.get("timestamp")
            dur = inf.get("duration")
            if ts is None or dur is None:
                n_missing_meta += 1
                continue
            pub = datetime.fromtimestamp(ts, tz=timezone.utc)
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
                "title": inf.get("title") or c["title"],
                "video_id": c["video_id"],
                "video_url": url,
                "duration_seconds": dur,
                "pub_date": pub.isoformat(),
            })

    print(f"  {channel['name']}: stages — "
          f"raw={n_raw}, title-match={n_title_match}, "
          f"shallow-dur-ok={n_shallow_dur_ok}, "
          f"missing-ts/dur={n_missing_meta}, "
          f"dropped-lookback={n_dropped_lookback}, "
          f"dropped-cap-fullmeta={n_dropped_full_dur}")
    return clips

# -----------------------------------------------------------------------------
# Audio download
# -----------------------------------------------------------------------------
def download_audio_stream(video_url, work_dir, source_tag, video_id):
    """Download the best audio-only stream from YouTube into work_dir.
    Returns the path to the downloaded file (m4a/webm/opus — yt-dlp picks)."""
    out_template = str(work_dir / f"{source_tag}_{video_id}.%(ext)s")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio",
        "outtmpl": out_template,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        raw_path = Path(ydl.prepare_filename(info))
    if not raw_path.exists():
        # Fallback if the extension resolved unexpectedly
        matches = list(work_dir.glob(f"{source_tag}_{video_id}.*"))
        if not matches:
            raise RuntimeError(f"yt-dlp downloaded file not found for {video_id}")
        raw_path = matches[0]
    return raw_path

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

    all_clips = []
    for channel in YOUTUBE_CHANNELS:
        clips = list_channel_clips(channel, lookback_hours)
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
        print("Dry run — skipping download + transcription")
        return [{**c, "transcript": None} for c in all_clips]

    transcripts = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for i, c in enumerate(all_clips):
            if i > 0:
                print("    (pausing 5s between clips)")
                time.sleep(5)

            print(f"  Transcribing: [{c['source_tag']}] {c['title'][:70]}...")
            try:
                raw_path = download_audio_stream(
                    c["video_url"], tmp_path, c["source_tag"], c["video_id"]
                )
                raw_size = os.path.getsize(raw_path)
                print(f"    downloaded {raw_size // 1024} KB raw "
                      f"({raw_path.suffix})")

                compressed = tmp_path / f"{c['source_tag']}_{c['video_id']}.mp3"
                compress_for_transcription(raw_path, compressed)
                compressed_size = os.path.getsize(compressed)
                print(f"    compressed to {compressed_size // 1024} KB (mono 48kbps)")

                if compressed_size > MAX_UPLOAD_BYTES:
                    raise RuntimeError(
                        f"compressed audio exceeds {MAX_UPLOAD_BYTES // 1024 // 1024}MB cap"
                    )

                text = transcribe_audio(compressed)
                text = normalize_names(text)
                if len(text) > TRANSCRIPT_CHAR_CAP:
                    text = text[:TRANSCRIPT_CHAR_CAP] + "...[truncated]"
                transcripts.append({
                    **c,
                    "transcript": text,
                    "transcript_chars": len(text),
                })
                print(f"    \u2713 {len(text):,} chars transcribed")
            except Exception as e:
                print(f"    ! transcription failed: {e}")
                transcripts.append({**c, "transcript": None, "error": str(e)})

    return transcripts

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

    results = pull_youtube(lookback_hours_override=override, dry=dry)
    print(f"\n{len(results)} clip(s):")
    for r in results:
        status = "dry" if r.get("transcript") is None and "error" not in r else \
                 ("error: " + r["error"]) if "error" in r else \
                 f"{r.get('transcript_chars', 0):,} chars"
        print(f"  [{r['source_tag']}] {r['title'][:60]} \u2014 {status}")
