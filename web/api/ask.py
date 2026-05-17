"""Vercel Python serverless function — streaming /api/ask endpoint.

Wraps the bot logic from repo-root bot.py over HTTP. Same model, system
prompt, and user-message construction as the CLI; just streams the
response chunk-by-chunk to the client.

Bot prompt and constants are imported from bot.py so the CLI and API
stay in sync — iterate the prompt in one place, both surfaces pick it
up.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Make bot_core importable from both contexts:
#   local:      web/api/ask.py → parents[1] = web/ (build-time copy of
#               bot_core.py via scripts/copy-data.mjs); parents[2] = repo root
#               (canonical bot_core.py) is also valid as a fallback
#   production: api/ask.py     → parents[1] = bundle root (bot_core.py copied
#               into web/ at build time, then bundled via includeFiles)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot_core import BOT_SYSTEM_PROMPT, MODEL, MAX_TOKENS, build_user_message  # noqa: E402

from anthropic import Anthropic  # noqa: E402


# Try repo-root data/ first (works under `vercel dev` against a working
# tree); fall back to web/data/ (populated by scripts/copy-data.mjs and
# bundled into the production function via vercel.json includeFiles).
_HISTORY_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "data" / "history.json",
    Path(__file__).resolve().parents[1] / "data" / "history.json",
]


def _load_history():
    for path in _HISTORY_CANDIDATES:
        if path.exists():
            return json.loads(path.read_text())
    raise FileNotFoundError(
        f"history.json not found in any of: {[str(p) for p in _HISTORY_CANDIDATES]}"
    )


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0) or 0)
        if content_length == 0:
            return self._json_error(400, "request body required")

        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return self._json_error(400, f"malformed JSON: {e}")

        if not isinstance(payload, dict):
            return self._json_error(400, "body must be a JSON object")

        question = (payload.get("question") or "").strip()
        if not question:
            return self._json_error(400, "question is empty or missing")

        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self._json_error(500, "ANTHROPIC_API_KEY is not set")

        try:
            history = _load_history()
        except FileNotFoundError as e:
            return self._json_error(500, str(e))

        # Open the streamed response. Once headers go out, we can't change
        # the status code if Anthropic later errors — best effort is to
        # write a trailing error marker and close.
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        # Disable proxy buffering so chunks reach the client immediately.
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            client = Anthropic()
            user_message = build_user_message(history, question)
            with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=BOT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    self.wfile.write(text.encode("utf-8"))
                    self.wfile.flush()
        except Exception as e:
            print(f"/api/ask streaming error: {e}", file=sys.stderr)
            try:
                self.wfile.write(f"\n\n[stream error: {e}]\n".encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

    def _json_error(self, status, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
