from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LANDING = Path(__file__).resolve().parent
SKILL_DIR = ROOT / "examples" / "status_email"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"

DEFAULT_PARAMS = {
    "recipient": "you@example.com",
    "subject": "Morning status - Skill Forge demo",
    "body": "Yesterday: wired the landing page to a local replay endpoint. Today: testing the email automation. Blockers: none.",
}

STATE_LOCK = threading.Lock()
SESSION_TOKEN = secrets.token_urlsafe(32)
STATE: dict[str, object] = {
    "running": False,
    "returncode": None,
    "message": "Idle",
    "output": "",
}


class LandingHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(LANDING), **kwargs)

    def do_POST(self) -> None:
        if self.path != "/run-demo":
            self.send_error(404)
            return
        if not request_is_authorized(self.headers, SESSION_TOKEN):
            self._json(403, {"ok": False, "message": "Invalid local demo session."})
            return

        with STATE_LOCK:
            if STATE["running"]:
                self._json(409, {"ok": False, "message": "Automation is already running."})
                return
            STATE.update(
                running=True,
                returncode=None,
                message="Starting Mail automation...",
                output="",
            )

        thread = threading.Thread(target=run_status_email, daemon=True)
        thread.start()
        self._json(202, {"ok": True, "message": "Mail automation started."})

    def do_GET(self) -> None:
        if self.path == "/automation-session":
            self._json(200, {"token": SESSION_TOKEN})
            return
        if self.path == "/automation-status":
            if not request_is_authorized(self.headers, SESSION_TOKEN):
                self._json(403, {"ok": False, "message": "Invalid local demo session."})
                return
            with STATE_LOCK:
                payload = dict(STATE)
            self._json(200, payload)
            return
        super().do_GET()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src https://fonts.gstatic.com",
        )
        super().end_headers()


def request_is_authorized(headers, expected_token: str) -> bool:
    """Require an unguessable custom header and reject non-local browser origins."""
    if not secrets.compare_digest(headers.get("X-Skill-Forge-Token", ""), expected_token):
        return False
    origin = headers.get("Origin")
    if not origin:
        return True
    try:
        hostname = urlparse(origin).hostname
    except ValueError:
        return False
    return hostname in {"127.0.0.1", "localhost", "::1"}


def run_status_email() -> None:
    python = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    cmd = [
        str(python),
        "-m",
        "skill_forge.cli",
        "replay",
        str(SKILL_DIR),
        "--params",
        json.dumps(DEFAULT_PARAMS),
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        message = (
            "Mail automation finished."
            if proc.returncode == 0
            else f"Mail automation failed with exit code {proc.returncode}."
        )
        with STATE_LOCK:
            STATE.update(
                running=False,
                returncode=proc.returncode,
                message=message,
                output=proc.stdout[-4000:],
            )
    except Exception as exc:  # noqa: BLE001 - surfaced in the local UI for debugging.
        with STATE_LOCK:
            STATE.update(
                running=False,
                returncode=1,
                message=f"Mail automation failed: {exc}",
                output="",
            )


def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), LandingHandler)
    print(f"Serving Skill Forge landing page at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
