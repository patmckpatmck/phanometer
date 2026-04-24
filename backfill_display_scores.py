#!/usr/bin/env python3
"""
One-off backfill: rewrite historical records so display_score = reactive_score.

Prior to 2026-04-23 the display score was a confidence-weighted blend of the
reactive score and the 30-day EWMA baseline. That blend muted the headline
number on days when sentiment diverged sharply from recent history. We removed
the blend and now show the reactive score directly (see phanometer.py).

This script walks data/history.json and every data/YYYY-MM-DD.json, sets
display_score = reactive_score, recomputes mood_label from the new display
score, and preserves every other field. Run once; keep in the repo for
reference.

Usage:
    python3 backfill_display_scores.py         # dry run — show what would change
    python3 backfill_display_scores.py --write # actually rewrite the files
"""

import json
import sys
from pathlib import Path

from phanometer import mood_label

DATA_DIR = Path(__file__).parent / "data"


def backfill_record(record):
    """Return (changed, new_record). Mutates nothing in place."""
    new = dict(record)
    reactive = record.get("reactive_score")
    if reactive is None:
        return False, new
    new["display_score"] = reactive
    new["mood_label"] = mood_label(reactive)
    changed = (
        new["display_score"] != record.get("display_score")
        or new["mood_label"] != record.get("mood_label")
    )
    return changed, new


def main():
    write = "--write" in sys.argv
    mode = "WRITE" if write else "DRY RUN"
    print(f"[{mode}] Backfilling display_score = reactive_score\n")

    history_path = DATA_DIR / "history.json"
    if not history_path.exists():
        print(f"  ! {history_path} does not exist — nothing to backfill.")
        return

    history = json.loads(history_path.read_text())
    changed_count = 0
    new_history = []

    for record in history:
        changed, new_record = backfill_record(record)
        new_history.append(new_record)
        if changed:
            changed_count += 1
            print(
                f"  {record['date']}: display_score "
                f"{record.get('display_score')} → {new_record['display_score']}, "
                f"mood_label {record.get('mood_label')!r} → {new_record['mood_label']!r}"
            )

            daily_path = DATA_DIR / f"{record['date']}.json"
            if daily_path.exists():
                daily = json.loads(daily_path.read_text())
                _, new_daily = backfill_record(daily)
                if write:
                    daily_path.write_text(json.dumps(new_daily, indent=2))
            else:
                print(f"    (no per-day file at {daily_path})")

    if write:
        history_path.write_text(json.dumps(new_history, indent=2))

    print(
        f"\n  {changed_count} of {len(history)} records "
        f"{'rewritten' if write else 'would be rewritten'}."
    )
    if not write:
        print("  Re-run with --write to apply.")


if __name__ == "__main__":
    main()
