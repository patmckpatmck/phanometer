#!/usr/bin/env python3
"""
Phan-o-meter attendance module.

Pulls recent Phillies home games from the free MLB Stats API, computes
attendance as % of Citizens Bank Park capacity, and reports deviation from
a trailing baseline window.

No API key required. MLB Stats API is free and public.

This is an INDEPENDENT hard signal — it is NOT one of the seven sentiment
dimensions. It's a behavioral proxy ("what fans actually do") that lives
alongside the social-text sentiment score.
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
PHILLIES_TEAM_ID     = 143           # MLB Stats API team ID
CBP_VENUE_ID         = 2681          # Citizens Bank Park venue ID (filters out spring training)
CBP_CAPACITY         = 42_901        # Current published capacity (2026)
LOOKBACK_DAYS        = 14            # Recent window (roughly 2 weeks / one long homestand)
MIN_BASELINE_GAMES   = 20            # Need this many prior-year games for a reliable baseline
PRIOR_YEAR_WINDOW    = 45            # Days before/after today to look at in prior season
CANARY_THRESHOLD     = -5.0          # Recent avg this many points below baseline = canary

MLB_BASE = "https://statsapi.mlb.com/api/v1"

# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------
def _fetch_json(url, params=None, timeout=15):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "phanometer/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)

def _get_schedule(start_date, end_date, team_id=PHILLIES_TEAM_ID):
    """Fetch team schedule between dates. Returns flat list of game dicts."""
    data = _fetch_json(
        f"{MLB_BASE}/schedule",
        {
            "sportId":   1,
            "teamId":    team_id,
            "startDate": start_date,
            "endDate":   end_date,
            "hydrate":   "gameInfo,venue",
        },
    )
    games = []
    for date_block in data.get("dates", []):
        games.extend(date_block.get("games", []))
    return games

def _attendance_from_boxscore(game_pk):
    """Fallback: the boxscore endpoint usually lists attendance in info[]."""
    try:
        data = _fetch_json(f"{MLB_BASE}/game/{game_pk}/boxscore")
        for item in data.get("info", []):
            if item.get("label") in ("Att", "Attendance"):
                raw = (item.get("value") or "").replace(",", "").replace(".", "").strip()
                return int(raw) if raw.isdigit() else None
    except Exception:
        pass
    return None

def _extract_attendance(game):
    """Attendance can appear in multiple places depending on hydration."""
    gi = game.get("gameInfo") or {}
    if gi.get("attendance"):
        return int(gi["attendance"])
    if game.get("attendance"):
        return int(game["attendance"])
    pk = game.get("gamePk")
    if pk:
        return _attendance_from_boxscore(pk)
    return None

def _result_string(game):
    home_score = game["teams"]["home"].get("score")
    away_score = game["teams"]["away"].get("score")
    if home_score is None or away_score is None:
        return "?"
    if home_score > away_score:
        return f"W {home_score}-{away_score}"
    if away_score > home_score:
        return f"L {home_score}-{away_score}"
    return f"T {home_score}-{away_score}"

# -----------------------------------------------------------------------------
# Core logic
# -----------------------------------------------------------------------------
def _home_games_in_range(start_date, end_date):
    """Return list of completed Phillies HOME games at Citizens Bank Park with attendance filled in.
    Venue filter excludes spring training (Clearwater) and any neutral-site games."""
    out = []
    for game in _get_schedule(start_date, end_date):
        if game["teams"]["home"]["team"]["id"] != PHILLIES_TEAM_ID:
            continue
        if game.get("venue", {}).get("id") != CBP_VENUE_ID:
            continue  # skip Grapefruit League games at BayCare Ballpark
        if game.get("status", {}).get("detailedState") != "Final":
            continue  # skip postponed, in-progress, etc.
        att = _extract_attendance(game)
        if att is None:
            continue
        date_str = game["gameDate"][:10]
        out.append({
            "game_pk":      game.get("gamePk"),
            "date":         date_str,
            "day_of_week":  datetime.strptime(date_str, "%Y-%m-%d").strftime("%A"),
            "opponent":     game["teams"]["away"]["team"]["name"],
            "result":       _result_string(game),
            "attendance":   att,
            "pct_capacity": round(100 * att / CBP_CAPACITY, 1),
            "day_night":    game.get("dayNight", "?"),
        })
    out.sort(key=lambda g: g["date"])
    return out

def pull_attendance(today=None):
    """
    Returns the attendance signal ready to merge into the daily record.

    Baseline strategy:
      - Use prior-year same-calendar-window (e.g. Mar/Apr 2025 when it's Mar/Apr 2026).
      - This avoids early-season / cold-weather / weak-opponent bias that a 60-day
        rolling current-season window would introduce.
      - Falls back to current-season prior games if prior-year data is also thin.
    """
    today = today or datetime.now(timezone.utc).date()
    recent_start = today - timedelta(days=LOOKBACK_DAYS)

    # Prior-year same-calendar-window, e.g. ±45 days from today's date last year
    last_yr_today = today.replace(year=today.year - 1)
    last_yr_start = last_yr_today - timedelta(days=PRIOR_YEAR_WINDOW)
    last_yr_end   = last_yr_today + timedelta(days=PRIOR_YEAR_WINDOW)

    try:
        recent = _home_games_in_range(recent_start.isoformat(), today.isoformat())
        baseline = _home_games_in_range(last_yr_start.isoformat(), last_yr_end.isoformat())
        baseline_source = f"{last_yr_today.year} same-calendar-window"

        # Fallback: if prior-year window is thin (new team? data gap?), use current-year
        # prior games that aren't in the recent window.
        if len(baseline) < MIN_BASELINE_GAMES:
            season_start = today.replace(month=3, day=1)  # roughly opening day cushion
            current_year_prior = _home_games_in_range(
                season_start.isoformat(),
                recent_start.isoformat(),
            )
            if len(current_year_prior) > len(baseline):
                baseline = current_year_prior
                baseline_source = f"{today.year} prior games (prior-year window was thin)"
    except Exception as e:
        return {"status": "error", "error": str(e), "recent_games": []}

    if not recent:
        return {
            "status": "no_recent_home_games",
            "recent_window_days": LOOKBACK_DAYS,
            "recent_games": [],
        }

    recent_avg = sum(g["pct_capacity"] for g in recent) / len(recent)
    baseline_avg = (
        sum(g["pct_capacity"] for g in baseline) / len(baseline)
        if baseline
        else recent_avg  # bootstrap: no baseline data at all
    )
    delta = recent_avg - baseline_avg

    return {
        "status":                 "ok",
        "capacity":               CBP_CAPACITY,
        "recent_window_days":     LOOKBACK_DAYS,
        "baseline_source":        baseline_source if baseline else "none",
        "recent_games_count":     len(recent),
        "recent_avg_pct":         round(recent_avg,   1),
        "baseline_games_count":   len(baseline),
        "baseline_avg_pct":       round(baseline_avg, 1),
        "delta_pct":              round(delta,        1),
        "canary_signal":          delta <= CANARY_THRESHOLD and len(baseline) >= MIN_BASELINE_GAMES,
        "recent_games":           recent,
    }

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    result = pull_attendance()
    print(json.dumps(result, indent=2))
    if result.get("status") == "ok":
        print(f"\nRecent: {result['recent_avg_pct']}% over {result['recent_games_count']} games")
        print(f"Baseline: {result['baseline_avg_pct']}% over {result['baseline_games_count']} games")
        print(f"Delta: {result['delta_pct']:+.1f} pts  {'🚨 CANARY' if result['canary_signal'] else '✓'}")
