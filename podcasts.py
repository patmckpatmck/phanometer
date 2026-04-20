#!/usr/bin/env python3
"""
Phan-o-meter podcast module.

Pulls recent episodes from curated Phillies podcasts, downloads the audio,
and transcribes with OpenAI Whisper.

Returns a list of transcript items shaped to slot into the same content
stream that Reddit posts feed into, so the scoring prompt sees everything
uniformly.

Usage:
    python podcasts.py                 # pull + transcribe last 24h
    python podcasts.py --hours 48      # custom lookback window
    python podcasts.py --dry           # skip transcription (test RSS only)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

# Phillies-flavored keywords used to filter WIP Daily (general Philly show)
PHILLIES_KEYWORDS = [
    # team / org
    "phillies", "phils", "bank park", "citizens bank", "thomson", "dombrowski",
    # current roster standouts fans talk about
    "harper", "schwarber", "wheeler", "sanchez", "nola", "painter", "walker",
    "bohm", "turner", "stott", "realmuto", "kerkering", "suarez", "luzardo",
    "garcia", "bader", "crawford", "sosa", "marchan",
    # narratives
    "rotation", "bullpen", "hitting coach", "kevin long", "rob thomson",
]

# RSS feeds to pull from. Each feed has a strategy:
#   "all"     → transcribe every recent episode
#   "filter"  → only transcribe if title matches PHILLIES_KEYWORDS
#
# Each feed also has a lookback_hours override so weekly podcasts don't get
# skipped by a 24h daily window.
PODCAST_FEEDS = [
    {
        "name": "Hittin' Season",
        "source_tag": "hittin_season",
        "voice": "fan_analyst",
        "apple_id": 1015394113,
        "strategy": "all",
        "lookback_hours": 36,  # published ~daily during season
    },
    {
        "name": "Phillies Therapy",
        "source_tag": "phillies_therapy",
        "voice": "beat_writer",  # Matt Gelb = The Athletic beat writer
        "apple_id": 1614847636,
        "strategy": "all",
        "lookback_hours": 192,  # weekly — so 8 day window catches fresh episode
    },
    {
        "name": "WIP Daily",
        "source_tag": "wip_daily",
        "voice": "radio_populist",
        "apple_id": 397184700,
        "strategy": "filter",
        "lookback_hours": 36,  # daily, Phillies-filtered
    },
    {
        "name": "Phillies Talk",
        "source_tag": "phillies_talk",
        "voice": "fan_analyst",  # NBC Sports Philadelphia team-beat show
        "apple_id": 1214369445,
        "strategy": "all",
        "lookback_hours": 96,  # publishes every 3-4 days
    },
    {
        "name": "The Phillies Show",
        "source_tag": "phillies_show",
        "voice": "fan_analyst",  # Foul Territory Network Phillies-specific show
        "apple_id": 1738537069,
        "strategy": "all",
        "lookback_hours": 72,  # publishes every ~2 days
    },
    {
        "name": "High Hopes",
        "source_tag": "high_hopes",
        "voice": "radio_populist",  # Audacy / 94WIP family, dedicated Phillies show
        "apple_id": 1304311183,
        "strategy": "all",
        "lookback_hours": 48,  # publishes daily-ish during games
    },
]

DEFAULT_LOOKBACK_HOURS = 24  # fallback if a feed doesn't specify
USER_AGENT = "phanometer/0.1 (daily Phillies sentiment tracker)"

# Transcription provider. Currently: OpenAI Whisper (paid, reliable rate limits).
# Previously: Groq Whisper Turbo (free but aggressive rate limits; developer tier upgrade
# was unavailable as of April 2026). Groq config kept commented for easy rollback.

# OpenAI Whisper config (active)
TRANSCRIPTION_API_URL = "https://api.openai.com/v1/audio/transcriptions"
TRANSCRIPTION_MODEL = "whisper-1"
TRANSCRIPTION_KEY_ENV = "OPENAI_API_KEY"

# Groq Whisper Turbo config (kept for easy rollback if OpenAI cost becomes a concern)
# TRANSCRIPTION_API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
# TRANSCRIPTION_MODEL = "whisper-large-v3-turbo"
# TRANSCRIPTION_KEY_ENV = "GROQ_API_KEY"

MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024  # 150 MB cap on raw audio download (safety valve)
MAX_UPLOAD_BYTES = 24 * 1024 * 1024     # 24 MB cap — OpenAI limit is 25 MB, leave headroom
COMPRESSED_BITRATE = "48k"              # mono 48kbps = ~21MB/hr, no accuracy loss on speech
TRANSCRIPT_CHAR_CAP = 80_000  # per episode — captures a full hour-long podcast
MAX_TRANSCRIPTIONS_PER_RUN = 4  # cost safeguard; newest-first, older episodes dropped
APPLE_LOOKUP_URL = "https://itunes.apple.com/lookup"

# -----------------------------------------------------------------------------
# RSS parsing
# -----------------------------------------------------------------------------

def _fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()

def _parse_pubdate(s):
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _title_matches_phillies(title):
    t = (title or "").lower()
    return any(kw in t for kw in PHILLIES_KEYWORDS)

def resolve_apple_feed(apple_id):
    """Use Apple's public lookup endpoint to get the canonical RSS URL for a podcast.
    This is more robust than hardcoding provider-specific URLs."""
    url = f"{APPLE_LOOKUP_URL}?id={apple_id}&entity=podcast"
    data = json.loads(_fetch(url).decode("utf-8"))
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"Apple lookup returned no results for id {apple_id}")
    feed_url = results[0].get("feedUrl")
    if not feed_url:
        raise RuntimeError(f"Apple lookup has no feedUrl for id {apple_id}")
    return feed_url

def parse_feed(feed, lookback_hours_override=None):
    """Fetch RSS via Apple lookup, return list of episode dicts within lookback window."""
    hours = lookback_hours_override or feed.get("lookback_hours") or DEFAULT_LOOKBACK_HOURS
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        rss_url = resolve_apple_feed(feed["apple_id"])
    except Exception as e:
        print(f"  ! {feed['name']}: Apple lookup failed ({e})")
        return []

    try:
        raw = _fetch(rss_url)
    except Exception as e:
        print(f"  ! {feed['name']}: failed to fetch RSS at {rss_url} ({e})")
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  ! {feed['name']}: failed to parse RSS ({e})")
        return []

    episodes = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        pubdate = _parse_pubdate(item.findtext("pubDate"))
        if not pubdate or pubdate < cutoff:
            continue

        # Enclosure URL = the audio file
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url") if enclosure is not None else None
        if not audio_url:
            continue

        # Apply title filter for filtered feeds
        if feed["strategy"] == "filter" and not _title_matches_phillies(title):
            continue

        episodes.append({
            "feed_name": feed["name"],
            "source_tag": feed["source_tag"],
            "voice": feed["voice"],
            "title": title,
            "audio_url": audio_url,
            "pub_date": pubdate.isoformat(),
        })

    return episodes

# -----------------------------------------------------------------------------
# Audio download + transcription
# -----------------------------------------------------------------------------

def download_audio(url, dest_path):
    """Download audio file with a generous size cap as a safety valve."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError(
                        f"audio exceeds {MAX_DOWNLOAD_BYTES // 1024 // 1024}MB safety cap"
                    )
                f.write(chunk)
    return total

def compress_for_transcription(src_path, dest_path):
    """Re-encode audio to mono 48kbps MP3 so it fits under the 25MB upload limit.
    Whisper accuracy is unaffected at this bitrate for speech content.
    Requires ffmpeg on PATH."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(src_path),
                "-ac", "1",              # mono
                "-b:a", COMPRESSED_BITRATE,
                "-ar", "16000",          # 16kHz sample rate — Whisper's native rate
                str(dest_path),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        return os.path.getsize(dest_path)
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found on PATH — install with `brew install ffmpeg`"
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg compression failed: {e.stderr.decode()[:200]}")

def transcribe_audio(audio_path):
    """POST multipart form to the configured Whisper endpoint with rate-limit retry.

    On 429 (rate limit): honor Retry-After header if present, else wait 60s, try again.
    Max 3 attempts.
    """
    for attempt in range(3):
        try:
            return _transcribe_audio_once(audio_path)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                # Prefer server-provided retry window; fall back to 60s
                retry_after = e.headers.get("retry-after")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
                print(f"    429 rate-limited, waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            raise

def _transcribe_audio_once(audio_path):
    api_key = os.environ.get(TRANSCRIPTION_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"{TRANSCRIPTION_KEY_ENV} not set in environment")

    # Build multipart body by hand to avoid adding a requests/httpx dependency
    boundary = "----phanometer" + os.urandom(8).hex()
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    filename = os.path.basename(audio_path)
    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="model"\r\n\r\n'.encode())
    parts.append(f"{TRANSCRIPTION_MODEL}\r\n".encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="response_format"\r\n\r\n'.encode())
    parts.append("text\r\n".encode())
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    parts.append(b"Content-Type: audio/mpeg\r\n\r\n")
    parts.append(audio_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        TRANSCRIPTION_API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return resp.read().decode("utf-8").strip()

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def pull_podcasts(lookback_hours_override=None, dry=False):
    """Return a list of transcript items for the last N hours across all feeds.

    If lookback_hours_override is None, each feed uses its per-feed lookback_hours.
    """
    if lookback_hours_override:
        print(f"Pulling podcasts (global override lookback {lookback_hours_override}h)...")
    else:
        print("Pulling podcasts (per-feed lookback windows)...")
    all_episodes = []
    for feed in PODCAST_FEEDS:
        episodes = parse_feed(feed, lookback_hours_override)
        window = lookback_hours_override or feed.get("lookback_hours", DEFAULT_LOOKBACK_HOURS)
        print(f"  {feed['name']} ({window}h window): {len(episodes)} episode(s)")
        all_episodes.extend(episodes)

    # Cost safeguard: cap transcriptions per run. Sort newest-first and drop the
    # rest so a prolific week (overlapping feed windows) can't blow up the bill.
    all_episodes.sort(key=lambda e: datetime.fromisoformat(e["pub_date"]), reverse=True)
    if len(all_episodes) > MAX_TRANSCRIPTIONS_PER_RUN:
        dropped = all_episodes[MAX_TRANSCRIPTIONS_PER_RUN:]
        all_episodes = all_episodes[:MAX_TRANSCRIPTIONS_PER_RUN]
        print(f"  Cap: keeping newest {MAX_TRANSCRIPTIONS_PER_RUN}, dropping "
              f"{len(dropped)} older episode(s):")
        for d in dropped:
            print(f"    - [{d['source_tag']}] {d['title'][:60]} ({d['pub_date']})")

    if dry:
        print("Dry run — skipping download + transcription")
        return [{**e, "transcript": None} for e in all_episodes]

    transcripts = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, ep in enumerate(all_episodes):
            # Small polite pause between episodes (harmless on OpenAI, was critical on Groq)
            if i > 0:
                print("    (pausing 5s between episodes)")
                time.sleep(5)

            print(f"  Transcribing: [{ep['source_tag']}] {ep['title'][:70]}...")
            try:
                # Sanitize filename
                safe = re.sub(r"[^a-z0-9]+", "_", ep["title"].lower())[:40] or "episode"
                src = Path(tmp) / f"{ep['source_tag']}_{safe}.src"
                compressed = Path(tmp) / f"{ep['source_tag']}_{safe}.mp3"

                raw_size = download_audio(ep["audio_url"], src)
                print(f"    downloaded {raw_size // 1024 // 1024} MB raw")

                compressed_size = compress_for_transcription(src, compressed)
                print(f"    compressed to {compressed_size // 1024 // 1024} MB "
                      f"({COMPRESSED_BITRATE} mono)")

                if compressed_size > MAX_UPLOAD_BYTES:
                    raise RuntimeError(
                        f"compressed audio still exceeds {MAX_UPLOAD_BYTES // 1024 // 1024}MB cap "
                        f"— try lower bitrate or chunking"
                    )

                text = transcribe_audio(compressed)
                if len(text) > TRANSCRIPT_CHAR_CAP:
                    text = text[:TRANSCRIPT_CHAR_CAP] + "...[truncated]"
                transcripts.append({
                    **ep,
                    "transcript": text,
                    "transcript_chars": len(text),
                })
                print(f"    ✓ {len(text):,} chars transcribed")
            except Exception as e:
                print(f"    ! transcription failed: {e}")
                transcripts.append({**ep, "transcript": None, "error": str(e)})

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

    # Load .env if running standalone
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    results = pull_podcasts(lookback_hours_override=override, dry=dry)
    print(f"\n{len(results)} total episode(s):")
    for r in results:
        status = "dry" if r.get("transcript") is None and "error" not in r else \
                 ("error: " + r["error"]) if "error" in r else \
                 f"{r.get('transcript_chars', 0):,} chars"
        print(f"  [{r['source_tag']}] {r['title'][:60]} — {status}")
