"""Render the compatibility replay wrapper for a data-only skill manifest."""

from __future__ import annotations

from skill_forge.pipeline.schema import Skill, validate_skill


def skill_to_replay_py(skill: Skill) -> str:
    validate_skill(skill)
    return _TEMPLATE.format(skill_name=skill.name, skill_description=skill.description)


_TEMPLATE = '''\
"""Auto-generated Skill Forge wrapper.

Skill: {skill_name}
{skill_description}

The validated ../skill.json manifest is the source of truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_forge.replay.runner import run_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description={skill_name!r})
    parser.add_argument("--params", default="{{}}", help="JSON object of parameters.")
    args = parser.parse_args()
    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        print(f"invalid --params JSON: {{exc}}", file=sys.stderr)
        return 2
    if not isinstance(params, dict):
        print("--params must decode to a JSON object", file=sys.stderr)
        return 2
    return run_manifest(Path(__file__).resolve().parents[1] / "skill.json", params)


if __name__ == "__main__":
    sys.exit(main())
'''
