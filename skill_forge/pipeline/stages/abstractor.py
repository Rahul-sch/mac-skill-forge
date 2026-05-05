from __future__ import annotations

import json

from skill_forge.pipeline import claude_client, prompts


def run(events: list[dict], segments: list[dict], model: str) -> list[dict]:
    """Pass only events that segments reference, with their original idx attached."""
    needed: set[int] = set()
    for seg in segments:
        for i in range(int(seg["start_idx"]), int(seg["end_idx"]) + 1):
            if 0 <= i < len(events):
                needed.add(i)
    sliced = [{"idx": i, **events[i]} for i in sorted(needed)]
    user = json.dumps({"segments": segments, "events": sliced}, default=str)
    result = claude_client.call_json(prompts.ABSTRACTOR_SYSTEM, user, model=model)
    return list(result.get("steps", []))
