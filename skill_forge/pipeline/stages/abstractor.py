from __future__ import annotations

import json

from skill_forge.pipeline import claude_client, prompts


def run(events: list[dict], segments: list[dict], model: str) -> list[dict]:
    """Pass ALL events with their indices, plus segments as advisory hints.

    Originally we sliced events to only those referenced by segments (token
    saver). That made the pipeline brittle to under-segmentation: if the
    segmenter only flagged a few "interesting" events, the abstractor never
    saw the surrounding clicks/keypresses and produced incomplete skills.
    For v0 traces (tens of events) sending the whole thing is cheap.
    """
    full = [{"idx": i, **e} for i, e in enumerate(events)]
    user = json.dumps({"segments": segments, "events": full}, default=str)
    result = claude_client.call_json(prompts.ABSTRACTOR_SYSTEM, user, model=model)
    return list(result.get("steps", []))
