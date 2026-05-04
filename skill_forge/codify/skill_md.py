"""Render a Skill to SKILL.md text. Pure function; output is byte-stable
so the snapshot tests in tests/test_codify.py can diff against fixtures."""

from __future__ import annotations

import json

from skill_forge.pipeline.schema import Parameter, Skill

_TYPE_PLACEHOLDER: dict[str, object] = {
    "string": "...",
    "number": 0,
    "file": "/path/to/file",
    "date": "2026-01-01",
}


def skill_to_md(skill: Skill) -> str:
    parts: list[str] = []
    parts.append("---")
    parts.append(f"name: {skill.name}")
    parts.append(f"description: {skill.description}")
    parts.append("---")
    parts.append("")
    parts.append(f"# {skill.name}")
    parts.append("")
    parts.append(skill.description)
    parts.append("")
    parts.append("## Parameters")
    if skill.parameters:
        for p in skill.parameters:
            parts.append(_param_line(p))
    else:
        parts.append("(none)")
    parts.append("")
    parts.append("## How to invoke")
    parts.append(f"Run: `python scripts/replay.py --params '{_example_params(skill)}'`")
    parts.append("")
    parts.append("## Steps (for reference; replay.py is the source of truth)")
    for i, step in enumerate(skill.steps, start=1):
        parts.append(f"{i}. {step.name}")
    parts.append("")
    return "\n".join(parts)


def _param_line(p: Parameter) -> str:
    qualifier = f"default={p.default}" if p.default is not None else "required"
    return f"- `{p.name}` ({p.type}, {qualifier}): {p.description}"


def _example_params(skill: Skill) -> str:
    if not skill.parameters:
        return "{}"
    example: dict[str, object] = {}
    for p in skill.parameters:
        if p.default is not None:
            example[p.name] = _coerce_default(p.default, p.type)
        else:
            example[p.name] = _TYPE_PLACEHOLDER.get(p.type, "...")
    return json.dumps(example)


def _coerce_default(value: str, type_: str) -> object:
    if type_ == "number":
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value
    return value
