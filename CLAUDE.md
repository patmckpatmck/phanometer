# CLAUDE.md

Guidance for Claude Code agents working in this repo. The README is for
humans reading the project; this file is for an agent about to make
changes. Read it before touching code.

## What this project is

Daily Philadelphia Phillies fan sentiment, scored from podcasts and the
MLB Stats API, fronted by a Next.js static site and a streaming
chatbot. Architecture and data flow are in `README.md`; this file
covers conventions, build commands, and gotchas accumulated during the
project's build.

## Offseason status (2026–27 winter) — read first

The project is in offseason mode as of October 2026. Several things this
file describes below are **currently switched off or absent from `main`**:

- **Daily pipeline is off.** The `Daily Phan-o-meter` workflow
  (`.github/workflows/daily.yml`) is disabled in the GitHub Actions UI —
  not in code. The YAML is unchanged. No scheduled API calls run.
  `data/history.json` is frozen at the final 2026 reading (2026-10-04).
- **Ask the Crowd is removed** (PR #40). `web/app/ask/`, `web/api/ask.py`,
  `web/components/ask/`, `HomeAskSection`, `MastheadAskLink`,
  `web/lib/ask.ts`, and `web/requirements.txt` are deleted; `vercel.json`
  only holds a `/ask → /` redirect. Root-level `bot.py` and `bot_core.py`
  still exist, and `copy-data.mjs` still copies `bot_core.py` into `web/`
  (harmless). Ask-related CSS remains in `globals.css`, unused.
- **Homepage is a season-in-review view** (PR #39): full-season chart
  (`web/components/SeasonTrend.tsx`), season stats, and a back-next-season
  message. `/day/[date]` archive pages are still live.
- **Metadata is past-tense** (PR #41): site description, dataset
  `temporalCoverage`, sitemap homepage `changeFrequency: 'monthly'`, and
  the DayNav "Season →" label (was "Today →").

### Spring restart checklist

Do these one at a time, in order. Each revert gets its own branch and PR.

1. **Check the runner.** GitHub → Settings → Actions → Runners:
   `phanometer-mini` should show Idle. If Offline, log in to the Mac Mini
   (it's a LaunchAgent; needs a GUI session).
2. **Check API keys and billing** before re-enabling: Anthropic, OpenAI,
   YouTube, X (the X API was returning HTTP 402 at season end). Secrets
   must be in both GitHub repo secrets and the `daily.yml` `env:` block.
3. **Revert the offseason PRs, newest first:** `4d3259a` (#41),
   `2f0946f` (#40), `f53630c` (#39). Each is a squash commit, so plain
   `git revert <sha>` works. If `ANTHROPIC_API_KEY` was removed from the
   Vercel project's env vars, re-add it before the #40 revert deploys,
   or `/api/ask` will 500.
4. **Decide how 2027 relates to 2026 data — open question, not decided.**
   `history.json` will append 2027 days onto 2026. Unresolved: whether the
   30-day baseline and trend should span the season boundary, whether to
   archive 2026 separately, and how the bot should treat last season.
   Ask Pat before changing anything here.
5. **Re-enable the workflow** in GitHub Actions (⋯ → Enable workflow),
   then trigger one manual run via `workflow_dispatch` and verify the
   commit before trusting the schedule.

## Build and run

```bash
# from repo root — Python pipeline
python3 phanometer.py            # full nightly run
python3 phanometer.py --dry      # skip Claude + transcription
python3 phanometer.py --no-reddit --no-podcasts --no-youtube
python3 podcasts.py --dry        # RSS-only smoke test
python3 bot.py "your question"   # CLI chatbot

# from web/ — frontend + serverless function
pnpm copy-data                   # copy data/history.json + bot_core.py into web/
pnpm dev                         # next dev (runs copy-data first)
pnpm build                       # next build (runs copy-data first)
vercel build --yes               # local Vercel build to inspect function bundle
```

**Env-loading idiom.** `.env` lives at the primary repo root only;
worktrees under `.claude/worktrees/` don't carry their own copy and
source it from there. `bot.py` and `phanometer.py` auto-load it on
direct invocation, but when you need to source it manually (running an
ad-hoc Python file, or shelling out from a worktree):

```bash
set -a; source <repo-root>/.env; set +a
```

## Python version

CI runs Python 3.12 (`.github/workflows/daily.yml`). Local development
on 3.9 currently works — no code in the repo uses `X | None` PEP 604
type syntax yet. If you add that syntax, also add
`from __future__ import annotations` at the top of the module so local
3.9 invocations don't break.

## Module layout

**Python (repo root):**

- `phanometer.py` — nightly orchestrator. Holds the scoring prompt,
  dimension weights, content-volume threshold.
- `podcasts.py` — RSS + Apple lookup → ffmpeg compression → OpenAI
  Whisper. `PODCAST_FEEDS` is the source of truth for feeds.
  `NAME_NORMALIZATIONS` post-processes Whisper misspellings.
- `attendance.py` — MLB Stats API client. `pull_attendance()` for the
  hard signal; `get_team_facts()` for the GROUND TRUTH block injected
  into scoring.
- `youtube.py` — YouTube Data API + `youtube-transcript-api`. Currently
  blocked on GH Actions IPs at the captions fetch step.
- `bot.py` — CLI development tool for the chatbot. One-shot
  `python3 bot.py "question"`. Imports its prompt and constants from
  `bot_core.py`.
- `bot_core.py` — `BOT_SYSTEM_PROMPT`, `MODEL`, `MAX_TOKENS`, and the
  user-message builder. Shared between `bot.py` and
  `web/api/ask.py`. Iterate the prompt here; both surfaces pick it up.

**Frontend and API (`web/`):**

- `web/app/page.tsx` — homepage server component.
- `web/app/ask/page.tsx` + `web/app/ask/StreamingAnswer.tsx` — `/ask`
  Q&A column. Server shell + client streamer.
- `web/api/ask.py` — Vercel Python serverless function. Streams Claude
  responses chunk-by-chunk.
- `web/scripts/copy-data.mjs` — runs before every build.
- `web/lib/ask.ts`, `web/lib/data.ts`, `web/components/ask/*` — chatbot
  UI building blocks.

## The build-time copy pattern

`web/scripts/copy-data.mjs` copies two things from the repo root into
`web/` before every build:

- `data/history.json` → `web/data/history.json`
- `bot_core.py` → `web/bot_core.py`

Both copies are in `web/.gitignore`. They regenerate on every build.

**Why this exists:** Vercel's `includeFiles` glob cannot traverse above
the project root (`web/` for this deploy). Without the copy step, the
serverless function bundle has no way to reach `bot_core.py` or
`data/history.json` at repo root.

**Do not edit the copies.** Edit the canonical `bot_core.py` at the
repo root; `data/history.json` is regenerated by the nightly cron and
should never be hand-edited. If you see a diff against `web/bot_core.py`
in `git status`, your gitignore is wrong, not the file.

## Vercel deployment gotchas

These all caused real incidents during the chatbot arc. Don't relearn:

- **`includeFiles` cannot escape the project root.** `..` paths in the
  glob are silently stripped. Hence the build-time copy pattern above.
- **Vercel's CI does not follow git symlinks during function bundling.**
  A symlinked file lands in the deployed bundle as a broken symlink;
  the function 500s with `ModuleNotFoundError` at import. We tried this
  approach for `bot_core.py` before settling on the copy-data fix.
- **`vercel dev` does not reliably serve Python functions** when Next.js
  is the primary runtime — `next dev` intercepts all routes. To verify
  the Python handler locally, run it as a standalone HTTP server using
  the venv that `vercel build` populates at `web/.vercel/python/.venv`,
  or push to a preview and verify there.
- **`output: 'export'` makes the Next.js app a fully static site.**
  Vercel's static-export routing intercepts `/api/*` before the
  function-routing layer unless `vercel.json` includes an explicit
  rewrite. The current config (`{ "source": "/api/:path*", "destination":
  "/api/:path*" }`) is what makes the `/api/ask` endpoint reachable.
- **Static export + `searchParams`.** With `output: 'export'`, server
  components cannot read `searchParams` at request time. Dynamic routes
  that need query params must use `useSearchParams()` from
  `next/navigation` in a client component, wrapped in `<Suspense>` to
  avoid build warnings. See `web/app/ask/page.tsx` for the pattern.

## The source-attribution rule

Load-bearing for both the scoring prompt and the bot's system prompt.

**Source identity — podcast names, platforms, voice tags ("reddit",
"fan_analyst", "beat_writer", "radio_populist", "youtube_fan",
"twitter_fan") — belongs in metadata fields only.** Never in narrative
prose generated by Claude.

- Metadata fields where attribution IS the purpose:
  `voice_breakdown[*].note`, `quotes[].source_hint`. Use human labels
  ("r/phillies", "fan analyst", "beat writer", "talk-radio host",
  "YouTube commenters", "X posts"), never the internal voice keys.
- Narrative-prose fields where attribution is FORBIDDEN: `reasoning`,
  `themes[].name`, `themes[].sample`, `quotes[].text` (must still be
  verbatim from input), the bot's answer body.

The bot's `BOT_SYSTEM_PROMPT` enforces this with a HARD RULE block
that names categories of forbidden patterns (person-attribution,
abstract-noun attribution, platform/source reference, passive
distancing) with examples and a self-check. The scoring prompt enforces
it with its own self-check. Editing either prompt to violate this rule
will degrade output across both surfaces.

## The bot's voice and copy rules

Documented in `bot_core.py`'s `BOT_SYSTEM_PROMPT`. Summary:

- No "yo," no faked accent, no cheesesteak props. No exclamation
  points. No emoji. No second-person flattery ("Great question!"). No
  hedging boilerplate ("As an AI..."). The tone comes from substance
  and rhythm, not props.
- Quote sparingly — one or two short verbatim quotes per response,
  woven into prose. Do not introduce quotes with attribution clauses
  ("one voice said," "as one fan put it") — those are forbidden by
  the attribution rule above.
- Use specific dates when they sharpen the answer ("the night Thomson
  got fired", "after the Atlanta sweep"), but don't pad with dates the
  question didn't ask about.
- Ground every claim in the history. When the corpus doesn't cover
  something, say so plainly — don't guess from general baseball
  knowledge.

The example questions on `/ask` and on the homepage section 04 are
fixed in `web/lib/ask.ts`. The voice calibration is the design — don't
rotate, A/B test, or let copywriters add to them.

## Git workflow

- Atomic commits. New work in branches off `main`, typically in Claude
  Code worktrees under `.claude/worktrees/`.
- Squash-merge on landing. Use the final commit message to describe the
  feature, not the iteration arc.
- Daily Phan-o-meter updates are committed by the GitHub Actions cron
  (`github-actions[bot]` author, `Daily Phan-o-meter update YYYY-MM-DD`
  message). If a manual commit conflicts with one of these, the
  recovery pattern is:

  ```bash
  git stash push -m "local-work" <files>
  git pull --rebase
  git push
  git stash pop
  ```

- The `data/` directory is committed; `data/last_failed_response.txt`
  shows up after a Claude JSON-parse failure and is debug output, not
  part of the daily record. Don't commit it.
- Never amend or force-push to `main`. The cron pushes here too — a
  rewrite would lose daily records.

## Working pattern

Pat strongly prefers one issue at a time. Don't bundle related work
without explicit invitation — even if it looks like an easy two-for-one.

Diagnose before fixing. Root causes documented in code comments help
future debugging more than a clever fix without context. When something
breaks in production, the first move is to read logs, not to patch.

When prompt instructions reference a file, constant, or behavior that
doesn't actually exist in the repo, **flag the discrepancy and ask**
rather than inventing the referenced thing. The chat-derived task
description is sometimes drafted against a remembered state of the
codebase that has since drifted. The repo is authoritative.
