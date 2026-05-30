# Phan-o-meter

Daily Philadelphia Phillies fan sentiment, scored from podcasts and the MLB
Stats API. Live at [phanometer.com](https://phanometer.com).

## What's shipped

Running nightly from GitHub Actions, with two user-facing surfaces:

- **Five curated Phillies podcasts** transcribed via OpenAI Whisper —
  Hittin' Season, Phillies Therapy, Phillies Talk, The Phillies Show,
  High Hopes. Each carries a voice tag (fan analyst / beat writer /
  talk-radio host) that the scoring prompt weights distinctly.
- **Reddit (r/phillies) ingestion.** Pulls recent posts, comments,
  and match-thread chatter via the Reddit Data API (authenticated
  read-only OAuth through PRAW). Treated as one of the six voice
  categories the scoring prompt weights distinctly.
- **YouTube clips** from 94WIP and similar channels — `youtube.py`
  resolves video metadata via the YouTube Data API and fetches
  captions via `youtube-transcript-api`, contributing to the
  talk-radio voice track alongside WIP podcast feeds.
- **YouTube fan comments** from the same channels — `youtube.py` pulls
  top-level comments via the Data API `commentThreads.list` endpoint
  (quota-metered, no caption scraping, so unaffected by the transcript
  IP block). These form their own raw-fan voice category, `youtube_fan`,
  kept distinct from the caption/talk-radio track.
- **X (Twitter) fan posts** — `twitter.py` runs an authenticated v2
  recent-search (`/2/tweets/search/recent`) over the 24h window for the
  `twitter_fan` voice. X is pay-per-use (billed per post returned), so
  the pull is hard-capped per run (~$0.75/day) well under the console
  spend cap. The query filters retweets, replies, and gambling/betting
  spam at the query level (so excluded posts are never returned or
  billed). Some media voice (beat writers, team/fan-brand accounts like
  Phillies Nation) still bleeds in alongside real fans — the known,
  accepted v1 limitation.
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
- **Daily vertical reel** for `@phanometer` on TikTok and Instagram
  Reels. A 1080×1920 self-contained HTML file is auto-generated each
  night from the day's JSON and served at `phanometer.com/reels`, which
  the iPhone home-screen icon points to. Six tap-to-advance frames
  (score, vibe, the seven dimensions, top cheer + groan quotes,
  attendance, outro) share the homepage's bell geometry, palette, and
  typography. Recorded by hand from the phone, then posted to TikTok
  first and Reels second. A pinned evergreen explainer at
  `phanometer.com/reels/about` introduces the project to new followers.
- **SEO foundations.** Distinct titles, descriptions, Open Graph and
  Twitter cards on every indexable page. Static OG card rendered at
  /assets/og-default.png. Robots.txt with surgical allow/disallow
  rules. Programmatic sitemap.xml via the Next.js metadata API.
  JSON-LD structured data (WebSite, Organization, Dataset). Semantic
  h1s and descriptive image alt text.

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
6. Writes `data/YYYY-MM-DD.json` and updates `data/history.json`.
7. Runs `reel/build.py`, which hydrates `reel/template.html` from
   today's JSON, re-encodes the bell and wordmark from
   `web/public/assets/` as inline base64, and writes
   `reels/phanometer-reel-YYYYMMDD.html` (the dated archive) plus
   `reels/index.html` (the stable URL the iPhone home-screen icon
   points to).
8. Commits `data/` and `reels/` together and pushes to `main`. The
   push triggers a Vercel rebuild; `web/scripts/copy-data.mjs` mirrors
   `reels/` into `web/public/reels/` so the dated reel and the stable
   URL deploy as static assets at `phanometer.com/reels/phanometer-reel-YYYYMMDD`
   and `phanometer.com/reels`.

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
  Resolves channel uploads, filters to clips inside the lookback
  window, and fetches captions that feed into the talk-radio voice.
  `pull_youtube_comments()` separately pulls top-level video comments
  via `commentThreads.list` for the `youtube_fan` voice (Data API only,
  not the caption scraper).
- `twitter.py` — X (Twitter) v2 recent-search client. `pull_tweets()`
  fetches recent Phillies fan posts (the `twitter_fan` voice) via
  `X_BEARER_TOKEN`, hard-capped per run for cost safety (X bills per
  post returned). `--search` runs a cheap capped smoke test.
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
  `data/history.json` into `web/data/`, `bot_core.py` into `web/`,
  and `reels/` into `web/public/reels/`. All three destinations are
  gitignored. Vercel's `includeFiles` glob can't traverse above the
  project root, so canonical files at repo root get mirrored inside
  `web/` at build time and bundled into the serverless function or
  shipped as static assets from there.

**Reel generator (`reel/` and `reels/`):**

- `reel/template.html` — design source for the daily social reel.
  Self-contained 1080×1920 vertical canvas with three placeholders
  (`__BELL_B64__`, `__WORDMARK_B64__`, `__REEL_DATA__`) that
  `reel/build.py` fills. Shares the homepage's bell geometry, color
  tokens, and font stack so the reel reads as a vertical re-cut of
  the site, not a parallel design. Honors the same source-attribution
  rule the scoring prompt does — source identity lives in the quote
  card's eyebrow and meta line, never in the quote prose.
- `reel/build.py` — generator. Reads the latest `data/YYYY-MM-DD.json`
  (or a date arg for re-rendering archives), re-encodes the bell and
  wordmark from `web/public/assets/` as inline base64 so any logo
  tweak ships in the next reel, and writes the dated output plus the
  stable `reels/index.html`. Same data file the frontend reads — no
  separate scoring pipeline.
- `reels/` — committed output directory.
  `reels/phanometer-reel-YYYYMMDD.html` is the dated archive (one per
  day, never overwritten). `reels/index.html` is overwritten each
  build as the stable home-screen URL. `reels/about/index.html` is
  an evergreen explainer reel, hand-written and untouched by the
  cron — pinned to the top of @phanometer on TikTok and Reels.
- **iOS standalone meta tags** on every reel HTML so iPhone Safari's
  "Add to Home Screen" launches them chrome-free, eliminating the URL
  bar from the screen recording.
- **Safe-area padding** is tuned for TikTok and Instagram Reels'
  overlays: the masthead sits below both platforms' top header
  strips, horizontal padding clears the right-side action rail
  (heart / comment / share), and bottom padding clears the username /
  caption / music attribution overlay. Same `560 200 360` frame
  padding is used on both the daily and explainer reels so the
  recording dance is identical for both.

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
**YouTube Data API:** key from Google Cloud Console.

**Reddit Data API:** required. Reddit returns `403` to unauthenticated
requests against its public JSON endpoints, so ingestion now goes
through authenticated read-only OAuth (PRAW). Register a **script** app
at https://www.reddit.com/prefs/apps — the free Data API tier is
non-commercial and capped at 100 QPM, no payment needed. Copy the
client ID and secret into `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`,
and set `REDDIT_USERNAME` so the request User-Agent is descriptive
(`phanometer/1.0 by u/<name>`).

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

# Build today's social reel from the most recent data/YYYY-MM-DD.json.
# Use a date arg to re-render a historical reel.
python3 reel/build.py
python3 reel/build.py 2026-05-19
```

## Daily cron

```yaml
# .github/workflows/daily.yml
on:
  schedule:
    - cron: '0 10 * * *'  # 10am UTC / 6am ET (DST) / 5am ET (standard)
  workflow_dispatch:
```

The job runs `python phanometer.py`, then `python reel/build.py`,
commits both `data/` and `reels/` changes, and pushes to `main`. The
push triggers a Vercel production deploy of the frontend with the new
`data/history.json` bundled into the `/api/ask` serverless function
and the new reel HTML deployed under `phanometer.com/reels/`.

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
    "reddit":         { "score": null, "note": null },
    "youtube_fan":    { "score": 44, "note": "..." },
    "twitter_fan":    { "score": 48, "note": "..." }
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
    "youtube_attempted": 3, "youtube_transcribed": 0, "youtube_chars": 0,
    "youtube_comments": 37, "youtube_comment_chars": 4200,
    "twitter_posts": 150, "twitter_post_chars": 18000
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
