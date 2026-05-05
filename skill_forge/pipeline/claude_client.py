"""LLM client for the pipeline.

Originally targeted Anthropic per Phase 5's plan; switched to Groq's
OpenAI-compatible chat/completions endpoint to work around Anthropic
billing. The wrapper shape (call_json) is provider-agnostic — every stage
calls call_json(system, user, model) and gets back parsed JSON.

Reads API key from GROQ_API_KEY (preferred) or ANTHROPIC_API_KEY (legacy
name still tolerated by the doctor).

Strips ```json fences if present. On parse failure dumps the raw response
to ./last_failed_response.json (gitignored) and raises BadJSONFromModel.
Up to max_attempts (default 2); no feedback-retry loop in v0.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class BadJSONFromModel(RuntimeError):
    def __init__(self, raw: str, attempt: int, parse_error: str) -> None:
        self.raw = raw
        self.attempt = attempt
        self.parse_error = parse_error
        super().__init__(
            f"model returned non-JSON after {attempt} attempt(s); raw saved to "
            f"last_failed_response.json. parser said: {parse_error}"
        )


def _api_key() -> str:
    key = os.environ.get("GROQ_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "no API key in env (set GROQ_API_KEY or ANTHROPIC_API_KEY)"
        )
    return key


def _post(payload: dict, timeout: float = 60.0, max_429_retries: int = 5) -> dict:
    """POST with automatic 429 backoff (honors Retry-After header when present)."""
    with httpx.Client(timeout=timeout) as client:
        for attempt in range(max_429_retries + 1):
            r = client.post(
                _GROQ_URL,
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if r.status_code != 429:
                r.raise_for_status()
                return r.json()
            # 429: back off and retry
            wait = _parse_retry_after(r.headers.get("retry-after"), attempt)
            log.warning(
                "groq 429 (attempt %d/%d); sleeping %.1fs",
                attempt + 1,
                max_429_retries + 1,
                wait,
            )
            time.sleep(wait)
        r.raise_for_status()  # will raise the last 429
        return r.json()


def _parse_retry_after(header: str | None, attempt: int) -> float:
    if header:
        try:
            return float(header) + 0.5
        except ValueError:
            pass
    return min(2.0 * (2**attempt), 30.0)  # 2, 4, 8, 16, 30s


def call_json(
    system: str,
    user: str,
    model: str,
    max_tokens: int = 4096,
    max_attempts: int = 2,
) -> Any:
    """Call the LLM with system+user and parse JSON output.

    Uses response_format=json_object so the model is constrained to emit
    valid JSON. Still strips fences defensively in case a future provider
    swap relaxes that.
    """
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }

    last_raw = ""
    last_err = ""
    for attempt in range(1, max_attempts + 1):
        data = _post(payload)
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            last_err = f"unexpected response shape: {e}"
            last_raw = json.dumps(data, indent=2)
            log.warning("attempt %d: %s", attempt, last_err)
            continue
        last_raw = text or ""
        try:
            return json.loads(_strip_fence(text))
        except json.JSONDecodeError as e:
            last_err = str(e)
            log.warning("attempt %d: JSON parse failed: %s", attempt, e)

    Path("last_failed_response.json").write_text(last_raw, encoding="utf-8")
    raise BadJSONFromModel(last_raw, max_attempts, last_err)


def _strip_fence(text: str) -> str:
    text = (text or "").strip()
    m = _FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return text
