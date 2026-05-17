# Phan-o-meter

Daily Philadelphia Phillies fan sentiment, scored from podcasts and the MLB
Stats API. Live at [phanometer.com](https://phanometer.com).

## What's shipped

Running nightly from GitHub Actions, with two user-facing surfaces:

- **Five curated Phillies podcasts** transcribed via OpenAI Whisper —
  Hittin' Season, Phillies Therapy, Phillies Talk, The Phillies Show,
  High Hopes. Each carries a voice tag (fan analyst / beat writer /
  talk-radio host) that the scoring prompt weights distinctly.
- **MLB attendance** hard signal from the Stats API — recent home-game
  capacity %, compared to a prior-year same-window baseline.
- **MLB Stats API ground-truth injection.** Each scoring call prepends an
  authoritative GROUND TRUTH block (W-L record, current streak, games
  back in the division) so Claude can't be misled by stale numbers a
  podcast host quoted before a recent series.
- **Claude-scored composite** across seven sentiment dimensions
  (`claude-sonnet-4-6`), with themes, attributed quotes, a one-sentence
  vibe summary, and a reasoning paragraph.
- **Static Next.js frontend** at `phanometer.com`, rebuilt on every data
  push, deployed on Vercel.
- **Streaming chatbot** at `phanometer.com/ask` — a one-question /
  one-answer Q&A column that streams a `claude-opus-4-5` answer grounded
  only in `data/history.json`. Same prompt and constants drive a CLI
  development tool (`bot.py`).

**Reddit (r/phillies) is intentionally disabled.** Reddit 403s cloud
provider IPs on its public JSON endpoints, which blocks GitHub Actions
runners. The nightly job runs with `--no-reddit`; `pull_reddit()` is
never called on the cron. The Reddit voice is rendered as "quiet today"
in the UI. Re-enable depends on a self-hosted runner on a residential
IP (see [What's next](#whats-next)). The code path is intact — drop
the flag in `.github/workflows/daily.yml`.

**YouTube clips** (94WIP and similar) are wired up but blocked by the
same problem. `youtube.py` resolves video metadata via the YouTube Data
API (which works from cloud IPs) but the captions fetch via
`youtube-transcript-api` is blocked by YouTube's anti-bot detection on
GitHub Actions IP ranges. `source_counts.youtube_attempted` reports
non-zero values; `youtube_transcribed` stays at zero. Same fix path as
Reddit.

## How it works

Nightly:

1. Pulls recent episodes from each podcast feed (RSS / Apple lookup),
   downloads audio, compresses with ffmpeg to fit Whisper's 25 MB limit,
   transcribes via OpenAI Whisper. Episodes outside each feed's lookback
   window are skipped. Transcripts are post-processed through a small
   normalization map (`NAME_NORMALIZATIONS` in `podcasts.py`) to catch
   known Whisper misspellings of roster names.
2. Pulls the current team record, streak, and games-back from the MLB
   Stats API.
3. Sends all transcripts plus the GROUND TRUTH block to Claude in one
   call. The structured prompt returns JSON scoring seven dimensions —
   results satisfaction, front office trust, manager confidence, lineup
   confidence, pitching confidence, health outlook, postseason belief —
   plus per-dimension confidence, per-voice scores and notes, themes,
   attributed quotes, a one-sentence vibe summary, a reasoning
   paragraph, and a `people_mentioned` array.
4. Pulls recent home-game attendance from the MLB Stats API and computes
   Citizens Bank Park capacity %, plus deviation from a prior-year
   same-window baseline. This is an **independent hard signal**, not a
   sentiment dimension — "what fans do" alongside "what fans say."
5. Computes a **reactive score** (dimension-weighted composite). When
   content volume clears `MIN_CONTENT_VOLUME = 30`, this is the
   **display score**. Below that, the day is flagged
   `insufficient_signal: true` and `display_score` is `null`. A 30-day
   EWMA baseline is also computed and stored — used by the frontend for
   the delta badge and the trend overlay, not blended into the display
   number.
6. Writes `data/YYYY-MM-DD.json` and updates `data/history.json`. The
   commit pushes to `main`, which triggers a Vercel rebuild of the
   frontend.

## Architecture

The repo is Python at the root for ingestion + scoring, and a Next.js
app under `web/` for the frontend and the chatbot's serverless endpoint.

**Python modules (repo root):**

- `phanometer.py` — orchestrates the nightly run. Calls into the other
  modules, holds the scoring prompt and dimension weights, writes the
  daily JSON.
- `podcasts.py` — RSS discovery, audio download and ffmpeg compression,
  OpenAI Whisper transcription, name normalization. `PODCAST_FEEDS`
  list is the source of truth for which feeds get pulled.
- `attendance.py` — MLB Stats API client. Exports `pull_attendance()`
  (the hard-signal computation) and `get_team_facts()` (the GROUND
  TRUTH block fed into scoring).
- `youtube.py` — YouTube Data API + `youtube-transcript-api` client.
  Currently unable to retrieve captions from GitHub Actions IPs.
- `bot.py` — CLI development tool for the chatbot. One-shot
  `python3 bot.py "question"`. Reads the same `data/history.json` the
  frontend reads, sends it to Claude with the bot's system prompt.
- `bot_core.py` — `BOT_SYSTEM_PROMPT`, `MODEL`, `MAX_TOKENS`, and the
  user-message builder, imported by both `bot.py` (CLI) and
  `web/api/ask.py` (the serverless function). Single source of truth
  for the bot's voice.

**Frontend and API (`web/`):**

- `web/app/page.tsx` — homepage. Server component, reads
  `data/history.json` at build time.
- `web/app/ask/page.tsx` + `web/app/ask/StreamingAnswer.tsx` — the
  `/ask` route. Server shell loads history and corpus stats at build
  time; the client component reads `?q=` via `useSearchParams()` and
  consumes the streaming `/api/ask` response.
- `web/api/ask.py` — Vercel Python serverless function. `POST` accepts
  `{"question": string}` and streams a plain-text response from Claude.
- `web/scripts/copy-data.mjs` — runs before every build. Copies
  `data/history.json` into `web/data/` and `bot_core.py` into `web/`,
  both gitignored. Vercel's `includeFiles` glob can't traverse above
  the project root, so the canonical files at repo root get mirrored
  inside `web/` at build time and bundled into the serverless
  function from there.

**Load-bearing design rules:**

- **Source-attribution rule.** Source identity (podcast names,
  platforms, voice tags) belongs in metadata fields only — `voice_breakdown`,
  `quotes[].source_hint`. It is forbidden from narrative-prose fields
  (`reasoning`, `themes[].sample`, the bot's answer body). Both the
  scoring prompt and the bot's system prompt enforce this with closed
  lists of forbidden patterns and self-check instructions. The
  attribution is rendered by the UI around these fields, so mentioning
  sources in the prose itself is both redundant and weakens the writing.
- **`postseason_belief` excludes coping framing.** Wild-card-era
  reassurance, "it's only April," recovery precedents from other teams'
  slow starts — all rebuttals to despair, not expressions of belief.
  When the only postseason-adjacent content is analysts telling fans to
  stay calm, `postseason_belief` stays low. Calibrated in the scoring
  prompt and load-bearing for accurate dimension readings during rough
  stretches.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in credentials
```

**Anthropic API:** get a key from https://console.anthropic.com/
**OpenAI API:** get a key from https://platform.openai.com/ (used for Whisper).
**YouTube Data API:** key from Google Cloud Console (currently optional
since captions fetch is blocked on GH Actions IPs).

Reddit credentials aren't required — ingestion is via raw `urllib`
against Reddit's public JSON endpoints (no auth), gated off by default
on the cron.

## Run

```bash
# Dry run (skips Claude + transcription — useful for testing ingestion)
python3 phanometer.py --dry

# Full run
./run.sh

# Skip podcasts (rate-limited or testing)
python3 phanometer.py --no-podcasts

# Ask the bot a question (CLI; requires ANTHROPIC_API_KEY)
python3 bot.py "How has the mood shifted since Mattingly took over?"
```

## Daily cron

```yaml
# .github/workflows/daily.yml
on:
  schedule:
    - cron: '0 10 * * *'  # 10am UTC / 6am ET (DST) / 5am ET (standard)
  workflow_dispatch:
```

The job runs `python phanometer.py --no-reddit`, commits any data
changes, and pushes to `main`. The push triggers a Vercel production
deploy of the frontend with the new `data/history.json` bundled into
the `/api/ask` serverless function.

## Output format

`data/2026-05-17.json`:

```json
{
  "date": "2026-05-17",
  "display_score": 55,
  "reactive_score": 55,
  "baseline_score": 51,
  "insufficient_signal": false,
  "content_volume": 87,
  "mood_label": "Touch and Go",
  "dimensions": {
    "results_satisfaction": 60,
    "pitching_confidence": 72,
    "...": "..."
  },
  "dimension_confidence": { "...": "..." },
  "voice_breakdown": {
    "fan_analyst":    { "score": 58, "note": "..." },
    "beat_writer":    { "score": 52, "note": "..." },
    "radio_populist": { "score": null, "note": null },
    "reddit":         { "score": null, "note": null }
  },
  "themes": [
    { "name": "...", "delta": -4, "sample": "..." }
  ],
  "quotes": [
    { "text": "...", "score": 60, "source_hint": "fan analyst (Hittin' Season)" }
  ],
  "vibe_summary": "...",
  "reasoning": "...",
  "people_mentioned": ["Harper", "Bohm", "Mattingly"],
  "source_counts": {
    "reddit_posts": 0, "reddit_comments": 0, "match_threads": 0,
    "podcasts_attempted": 5, "podcasts_transcribed": 2, "podcast_chars": 84000,
    "youtube_attempted": 3, "youtube_transcribed": 0, "youtube_chars": 0
  },
  "podcasts_used": [
    { "feed_name": "Hittin' Season", "voice": "fan_analyst", "title": "...", "chars": 48000 }
  ],
  "team_facts": { "record": "23-23", "streak": "W3", "games_behind": "8.0" },
  "hard_signals": {
    "attendance": {
      "status": "ok",
      "capacity": 42901,
      "baseline_source": "prior-year same window",
      "recent_avg_pct": 82.3,
      "baseline_avg_pct": 89.6,
      "delta_pct": -7.3,
      "canary_signal": true,
      "recent_games": [ { "date": "2026-05-16", "opponent": "Pirates", "result": "W 4-2", "attendance": 35420, "pct_capacity": 82.6 } ]
    }
  },
  "generated_at": "2026-05-17T10:08:00Z"
}
```

The frontend reads `data/history.json` for the trend chart, the latest
day's record for everything on the homepage, and serves it to the
`/api/ask` function as the chatbot's corpus.

`people_mentioned` shipped in the scoring prompt on 2026-05-17;
records generated from the next daily run forward will populate it.
Earlier records have the field absent.

### The `hard_signals` concept

Sentiment dimensions measure **what fans say**. Hard signals measure
**what fans do**. They live in a separate block so the frontend can
display them alongside — not inside — the main Phan-o-meter gauge. When
they diverge ("sentiment says Touch and Go but attendance is running 9
points below baseline"), that divergence is the interesting moment.

## Tuning

- **Dimension weights** — `DIMENSION_WEIGHTS` in `phanometer.py`.
  Results satisfaction is weighted highest because fan mood tracks
  wins/losses hardest.
- **Baseline responsiveness** — `alpha=0.3` in `compute_baseline()`.
  Higher alpha = baseline moves faster (less stable). Lower = more
  stubborn. The baseline shows up in the trend chart and the delta
  badge, not in `display_score`.
- **Insufficient-signal threshold** — `MIN_CONTENT_VOLUME = 30` in
  `phanometer.py`. Content volume is `reddit_items + audio_minutes`; a
  day below the threshold publishes `insufficient_signal: true` and a
  null `display_score` instead of a potentially noisy reading. A
  single ~30-minute podcast episode clears the bar.
- **Lookback** — `LOOKBACK_HOURS = 24`. Each day only pulls the last
  day of content. Older content is already baked into prior days'
  scores — the baseline carries long-term memory without stale quotes
  polluting today's prompt. Per-feed overrides in `PODCAST_FEEDS`
  extend the window for weekly podcasts.

## What's next

- **Residential-IP self-hosted GitHub Actions runner.** Single
  highest-leverage item. Simultaneously unblocks YouTube captions
  ingestion and re-enables Reddit ingestion — both currently fail
  because YouTube and Reddit block GitHub Actions IP ranges. Beelink
  SER-series Linux mini PCs (~$250) identified as candidate hardware.
- **Bell clapper / needle alignment bug.** Visual: on the homepage
  meter, the bell's clapper and the red needle arrow point at
  different tick marks. `useBellAngle` and `needleAngle` formulas
  need reconciling.
- **Post-generation attribution pass for the bot (optional).** A
  second Claude call whose only job is to rewrite attribution-shaped
  phrases in the bot's output. Only worth doing if leaks become a
  real problem in production traffic — the HARD RULE in the system
  prompt is currently catching most.
- **Expected-attendance regression model (optional).** Day-of-week,
  month, opponent, weather. The current prior-year same-window
  baseline is the v1 simplification; residuals from a real model
  would become a sharper canary signal.

**Shelved:** Resale market temperature (At the Gate). Designed and
prototyped a SeatGeek-based metric blending get-in price and listing
volume against a live MLB league cross-section. Shelved after
confirming SeatGeek's basic Catalog API tier returns empty `stats`
objects; pricing and listing counts are both gated behind their
affiliate program (revenue-share via Impact, requires embedded
purchase links). Not a fit for a non-commercial measurement project.

## Repo

Local: `~/phanometer`. GitHub: `patmckpatmck/phanometer`.
