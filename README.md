# Phan-o-meter

Daily Philadelphia Phillies fan sentiment, scored from r/phillies posts and comments.

## What's shipped

Running nightly from GitHub Actions:

- **Podcast transcription** (Phillies Therapy as beat-writer voice, Hittin' Season as fan-analyst voice) via OpenAI Whisper.
- **MLB attendance** hard signal from the Stats API.
- **Claude-scored composite** across seven sentiment dimensions, with themes, quotes, and reasoning.
- **Static Next.js site** at [phanometer.vercel.app](https://phanometer.vercel.app), rebuilt on every data push.

**Reddit (r/phillies) is paused.** Reddit 403s cloud provider IPs on its public JSON endpoints, which blocks GitHub Actions runners. The nightly job runs with `--no-reddit`; the Reddit voice renders as "quiet today" in the UI until the pipeline runs from a non-cloud host (self-hosted runner, VPS, or home server) or gains authenticated-OAuth access that Reddit accepts from cloud IPs. The `pull_reddit()` code path is intact and ready to re-enable — just drop the flag in `.github/workflows/daily.yml`.

Not yet built: WIP Daily (talk-radio voice), local news RSS, expected-attendance regression. See [Next steps](#next-steps-not-yet-built).

## How it works

Nightly, the script:

1. Pulls the last 24 hours of posts and comments from r/phillies via PRAW. Game threads get a bigger comment budget than regular posts — they're where the real-time emotion lives.
2. Sends everything to Claude in one call with a structured prompt that returns JSON scoring seven dimensions: results satisfaction, front office trust, manager confidence, lineup confidence, pitching confidence, health outlook, and postseason belief. Each dimension also gets a confidence score (how strong the signal was) and the model returns themes, representative quotes, and a reasoning paragraph.
3. Computes a **reactive score** (today's dimension-weighted composite), a **baseline** (30-day EWMA of prior reactive scores), and a **display score** (blend of the two, weighted toward reactive on high-volume days).
4. Pulls recent home-game attendance from the MLB Stats API and computes % of Citizens Bank Park capacity, plus deviation from the 60-day baseline. This is an **independent hard signal**, not a sentiment dimension — it's "what fans do" alongside "what fans say."
5. Writes `data/YYYY-MM-DD.json` and updates `data/history.json`.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in credentials
```

**Reddit app:** go to https://www.reddit.com/prefs/apps, create a "script" app, copy the client ID (under the app name) and secret.

**Anthropic API:** get a key from https://console.anthropic.com/

## Run

```bash
# Dry run (pulls Reddit, skips Claude — useful for testing)
python phanometer.py --dry

# Full run
./run.sh
```

## Daily cron

Same pattern as HR Scout. Either a cron on any machine, or a GitHub Action triggered nightly:

```yaml
# .github/workflows/daily.yml
on:
  schedule:
    - cron: '0 10 * * *'  # 10am UTC / 6am ET
  workflow_dispatch:
```

## Output format

`data/2026-04-18.json`:

```json
{
  "date": "2026-04-18",
  "display_score": 42,
  "reactive_score": 38,
  "baseline_score": 48,
  "mood_label": "Uneasy",
  "dimensions": {
    "results_satisfaction": 28,
    "pitching_confidence": 35,
    "...": "..."
  },
  "dimension_confidence": { "...": "..." },
  "themes": [
    { "name": "Bullpen struggles", "delta": -7, "sample": "..." }
  ],
  "quotes": [
    { "text": "...", "score": 22, "source_hint": "game thread comment" }
  ],
  "reasoning": "Team lost 4 of last 5...",
  "source_counts": { "reddit_posts": 47, "reddit_comments": 312, "match_threads": 3 },
  "hard_signals": {
    "attendance": {
      "status": "ok",
      "capacity": 42901,
      "recent_window_days": 10,
      "recent_games_count": 4,
      "recent_avg_pct": 82.3,
      "baseline_avg_pct": 91.0,
      "delta_pct": -8.7,
      "canary_signal": true,
      "recent_games": [ { "date": "2026-04-17", "opponent": "Braves", "result": "L 4-7", "attendance": 34820, "pct_capacity": 81.2, "day_of_week": "Friday" } ]
    }
  },
  "generated_at": "2026-04-18T10:00:00Z"
}
```

The frontend reads `data/history.json` for the trend chart and the latest day's file for everything else.

### The `hard_signals` concept

Sentiment dimensions measure **what fans say**. Hard signals measure **what fans do**. They live in a separate block so the frontend can display them alongside — not inside — the main Phan-o-meter gauge. When they diverge ("sentiment says Cautious but attendance is running 9 points below baseline"), that divergence is the interesting moment. Future hard signals to add: local sports-talk-radio caller volume, Phillies Twitter follower growth rate, jersey sales momentum (if any public source exists).

## Tuning

- **Dimension weights** — `DIMENSION_WEIGHTS` in `phanometer.py`. Results satisfaction is weighted highest because fan mood tracks wins/losses hardest. Tune based on what feels right after a few weeks of data.
- **Baseline responsiveness** — `alpha=0.3` in `compute_baseline()`. Higher alpha = baseline moves faster (less stable). Lower = baseline is more stubborn.
- **Reactive vs baseline blend** — `min(0.7, 0.3 + volume / 500.0)` in `compute_display_score()`. On high-volume days (game day, breaking news), the reactive score gets more weight.
- **Lookback** — `LOOKBACK_HOURS = 24`. Each day only pulls the last day of content. Older content is already baked into prior days' scores — the baseline carries long-term memory without stale quotes polluting today's prompt.

## Next steps (not yet built)

- **WIP Daily transcription** — grab the 94WIP daily podcast RSS, transcribe with Groq Whisper (~$0.01/day), add as a second text source.
- **YouTube comments** — curated channel IDs (Phillies Nation, MLB, Jomboy, Foul Territory, Barstool Philly) → `playlistItems.list` → `commentThreads.list`. ~100 quota units/day.
- **Local news RSS** — Inquirer, Phillies Nation, The Athletic Philly.
- **WIP full-show diarization** — separate "caller mood" from "host narrative" as distinct lines on the chart. v2 feature.
- **Expected-attendance model** — v1 compares to a flat 60-day baseline; v2 builds a small regression on day-of-week, month, opponent record, and weather so "expected" is context-aware. Residuals become the real canary signal.
- **Frontend** — Next.js app on Vercel that reads `data/history.json` and renders the Phan-o-meter UI.
