from __future__ import annotations

import json

from skill_forge.pipeline import claude_client, prompts


def run(parameterized: dict, model: str) -> dict:
    user = json.dumps(parameterized, default=str)
    return claude_client.call_json(prompts.VALIDATOR_SYSTEM, user, model=model)
