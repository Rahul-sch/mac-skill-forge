"""Versioned, data-only skill manifests used by the trusted replay runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from skill_forge.pipeline.schema import Parameter, Skill, Step, validate_skill

MANIFEST_VERSION = 1


def skill_to_manifest(skill: Skill) -> dict[str, Any]:
    validate_skill(skill)
    return {
        "version": MANIFEST_VERSION,
        "name": skill.name,
        "description": skill.description,
        "parameters": [
            {
                "name": parameter.name,
                "type": parameter.type,
                "description": parameter.description,
                "default": parameter.default,
            }
            for parameter in skill.parameters
        ],
        "steps": [
            {
                "name": step.name,
                "action": step.action,
                "selector": step.selector,
                "args": step.args,
                "assertions": step.assertions,
            }
            for step in skill.steps
        ],
    }


def manifest_to_json(skill: Skill) -> str:
    return json.dumps(skill_to_manifest(skill), indent=2, ensure_ascii=False) + "\n"


def load_manifest(path: Path) -> Skill:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read skill manifest {path}: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("version") != MANIFEST_VERSION:
        raise ValueError(f"unsupported or missing skill manifest version in {path}")
    try:
        skill = Skill(
            name=str(raw["name"]),
            description=str(raw["description"]),
            parameters=[
                Parameter(
                    name=str(item["name"]),
                    type=str(item["type"]),
                    description=str(item.get("description", "")),
                    default=None if item.get("default") is None else str(item["default"]),
                )
                for item in raw.get("parameters", [])
            ],
            steps=[
                Step(
                    name=str(item["name"]),
                    action=str(item["action"]),
                    selector=item.get("selector"),
                    args=dict(item.get("args", {})),
                    assertions=list(item.get("assertions", [])),
                )
                for item in raw.get("steps", [])
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed skill manifest {path}: {exc}") from exc
    return validate_skill(skill)
