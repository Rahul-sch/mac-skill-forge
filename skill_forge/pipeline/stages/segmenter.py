from __future__ import annotations

import json

from skill_forge.pipeline import claude_client, prompts


def run(events: list[dict], model: str) -> list[dict]:
    user = json.dumps(events, default=str)
    result = claude_client.call_json(prompts.SEGMENTER_SYSTEM, user, model=model)
    return list(result.get("segments", []))
