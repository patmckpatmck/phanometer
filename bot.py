#!/usr/bin/env python3
"""
Phan-o-meter chatbot — one-shot CLI.

Sends data/history.json plus the question to Claude and prints the answer.
Forward path: graduate this into the bot backend. For now, a thin script to
validate the chatbot concept end-to-end.

Usage:
  python3 bot.py "How has the mood shifted since Thomson was fired?"
"""

import json
import os
import sys
from pathlib import Path

from anthropic import Anthropic

from bot_core import BOT_SYSTEM_PROMPT, MAX_TOKENS, MODEL, build_user_message

# Load .env into environment if present, matching phanometer.py.
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

HISTORY_PATH = Path(__file__).parent / "data" / "history.json"


def _die(msg, code=1):
    print(f"bot.py: {msg}", file=sys.stderr)
    sys.exit(code)


def load_history():
    if not HISTORY_PATH.exists():
        _die(f"history file not found at {HISTORY_PATH}")
    try:
        return json.loads(HISTORY_PATH.read_text())
    except json.JSONDecodeError as e:
        _die(f"history file is malformed JSON: {e}")


def ask(question):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        _die("ANTHROPIC_API_KEY is not set")

    history = load_history()
    user_message = build_user_message(history, question)

    client = Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=BOT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return message.content[0].text


def main():
    if len(sys.argv) != 2:
        _die('usage: python3 bot.py "your question"', code=2)
    question = sys.argv[1].strip()
    if not question:
        _die("question is empty")
    print(ask(question))


if __name__ == "__main__":
    main()
