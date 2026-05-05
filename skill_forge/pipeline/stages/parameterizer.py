from __future__ import annotations

import json

from skill_forge.pipeline import claude_client, prompts


def run(steps: list[dict], model: str) -> dict:
    user = json.dumps(steps, default=str)
    return claude_client.call_json(prompts.PARAMETERIZER_SYSTEM, user, model=model)
