"""Build the daily reel HTML from the most recent data/YYYY-MM-DD.json.

Reads reel/template.html and substitutes three placeholders:

    __BELL_B64__       base64 of web/public/assets/bell.png
    __WORDMARK_B64__   base64 of web/public/assets/wordmark.png
    __REEL_DATA__      JSON literal of the day's REEL_DATA payload

Writes the rendered HTML to reels/phanometer-reel-YYYYMMDD.html at the
repo root. The web build step (web/scripts/copy-data.mjs) then copies
reels/ into web/public/reels/ so each file is served at
phanometer.com/reels/phanometer-reel-YYYYMMDD.html after the next
Vercel deploy.

Usage:

    python3 reel/build.py             # build for today's data
    python3 reel/build.py 2026-05-19  # build for a specific date

Pinning a date is for re-rendering historical entries; the cron uses
the no-arg form which picks the most recent data file.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "reel" / "template.html"
DATA_DIR = REPO_ROOT / "data"
BELL_PATH = REPO_ROOT / "web" / "public" / "assets" / "bell.png"
WORDMARK_PATH = REPO_ROOT / "web" / "public" / "assets" / "wordmark.png"
OUTPUT_DIR = REPO_ROOT / "reels"


def latest_data_file() -> Path:
    files = sorted(DATA_DIR.glob("????-??-??.json"))
    if not files:
        raise SystemExit(f"no data files in {DATA_DIR}")
    return files[-1]


def data_file_for(date: str) -> Path:
    path = DATA_DIR / f"{date}.json"
    if not path.exists():
        raise SystemExit(f"no data file for {date} at {path}")
    return path


def build_reel_data(daily: dict) -> dict:
    """Project the daily JSON down to the fields the reel actually displays.

    The reel's render() picks highest/lowest quote by score at runtime,
    so we hand it the full quotes[] array unchanged. attendance is
    flattened to the four numbers the reel needs; everything else in
    hard_signals (recent_games, etc.) is dropped.
    """
    att = (daily.get("hard_signals") or {}).get("attendance") or {}
    return {
        "date": daily["date"],
        "display_score": daily["display_score"],
        "baseline_score": daily["baseline_score"],
        "mood_label": daily.get("mood_label"),
        "vibe_summary": daily.get("vibe_summary") or "",
        "dimensions": daily["dimensions"],
        "quotes": daily.get("quotes") or [],
        "attendance": {
            "recent_avg_pct": att.get("recent_avg_pct"),
            "baseline_avg_pct": att.get("baseline_avg_pct"),
            "delta_pct": att.get("delta_pct"),
            "canary_signal": bool(att.get("canary_signal", False)),
        },
    }


def encode_b64(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"missing asset: {path}")
    return base64.b64encode(path.read_bytes()).decode("ascii")


def main(argv: list[str]) -> None:
    data_path = data_file_for(argv[1]) if len(argv) > 1 else latest_data_file()
    daily = json.loads(data_path.read_text())
    date = daily["date"]

    reel_data = build_reel_data(daily)
    bell_b64 = encode_b64(BELL_PATH)
    wordmark_b64 = encode_b64(WORDMARK_PATH)

    template = TEMPLATE_PATH.read_text()

    # JSON is a valid JS expression, so dumping the dict directly into
    # the `const REEL_DATA = __REEL_DATA__;` slot just works. Indent for
    # readability — the file is meant to be human-inspectable.
    payload = json.dumps(reel_data, indent=2, ensure_ascii=False)

    rendered = (
        template
        .replace("__BELL_B64__", bell_b64)
        .replace("__WORDMARK_B64__", wordmark_b64)
        .replace("__REEL_DATA__", payload)
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"phanometer-reel-{date.replace('-', '')}.html"
    out_path.write_text(rendered)
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(rendered):,} bytes)")

    # Also write the same content to reels/index.html so phanometer.com/reels/
    # is a stable URL the user can save to the iPhone home screen. The dated
    # file stays as the archive; index.html is overwritten on each build.
    latest_path = OUTPUT_DIR / "index.html"
    latest_path.write_text(rendered)
    print(f"wrote {latest_path.relative_to(REPO_ROOT)} (stable URL)")


if __name__ == "__main__":
    main(sys.argv)
