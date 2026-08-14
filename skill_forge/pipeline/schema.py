"""Frozen schema for skills, steps, and parameters.

The action set is the contract between codify (Phase 3), the LLM pipeline
(Phase 5), and the replayer (Phase 4). Do NOT add new actions speculatively
("scroll", "drag", etc.) — expand only when a real workflow needs them.

The placeholder syntax in step args is `${param_name}`. Frozen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

VALID_ACTIONS: frozenset[str] = frozenset(
    {"click", "type", "press_key", "wait", "app_launch", "scroll"}
)
VALID_PARAMETER_TYPES: frozenset[str] = frozenset({"string", "number", "file", "date"})
VALID_MODIFIERS: frozenset[str] = frozenset({"cmd", "shift", "opt", "ctrl"})

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class SkillValidationError(ValueError):
    """Raised when an LLM-produced skill violates the replay contract."""


@dataclass
class Step:
    name: str
    action: str
    selector: str | None
    args: dict[str, Any]
    assertions: list[str]


@dataclass
class Parameter:
    name: str
    type: str  # "string" | "number" | "file" | "date"
    description: str
    default: str | None


@dataclass
class Skill:
    name: str
    description: str
    parameters: list[Parameter]
    steps: list[Step]


def validate_skill(skill: Skill) -> Skill:
    """Validate the complete LLM/runtime boundary before emitting or replaying."""
    errors: list[str] = []
    if not _SKILL_NAME_RE.fullmatch(skill.name) or len(skill.name) > 30:
        errors.append("skill name must be kebab-case and at most 30 characters")
    if not skill.description.strip():
        errors.append("skill description must not be empty")
    if not skill.steps:
        errors.append("skill must contain at least one step")

    parameter_names: set[str] = set()
    for index, parameter in enumerate(skill.parameters, start=1):
        prefix = f"parameter {index} ({parameter.name!r})"
        if not _NAME_RE.fullmatch(parameter.name):
            errors.append(f"{prefix}: name must be a valid identifier")
        if parameter.name in parameter_names:
            errors.append(f"{prefix}: duplicate parameter name")
        parameter_names.add(parameter.name)
        if parameter.type not in VALID_PARAMETER_TYPES:
            errors.append(f"{prefix}: unsupported type {parameter.type!r}")

    referenced: set[str] = set()
    for index, step in enumerate(skill.steps, start=1):
        prefix = f"step {index} ({step.name!r})"
        if not step.name.strip():
            errors.append(f"{prefix}: name must not be empty")
        if step.action not in VALID_ACTIONS:
            errors.append(f"{prefix}: unsupported action {step.action!r}")
            continue
        if not isinstance(step.args, dict):
            errors.append(f"{prefix}: args must be an object")
            continue
        if not isinstance(step.assertions, list) or not all(
            isinstance(item, str) for item in step.assertions
        ):
            errors.append(f"{prefix}: assertions must be a list of strings")

        referenced.update(_placeholders(step.selector or ""))
        for value in step.args.values():
            if isinstance(value, str):
                referenced.update(_placeholders(value))

        if step.action == "click" and not step.selector:
            coords = step.args.get("coordinates")
            if not _valid_coordinates(coords):
                errors.append(f"{prefix}: click needs a selector or [x, y] coordinates")
        elif step.action == "type" and not isinstance(step.args.get("text"), str):
            errors.append(f"{prefix}: type needs a string text argument")
        elif step.action == "press_key":
            keycode = step.args.get("keycode")
            modifiers = step.args.get("modifiers", [])
            if not isinstance(keycode, int) or isinstance(keycode, bool) or not 0 <= keycode <= 255:
                errors.append(f"{prefix}: keycode must be an integer from 0 to 255")
            if not isinstance(modifiers, list) or any(m not in VALID_MODIFIERS for m in modifiers):
                errors.append(f"{prefix}: modifiers contain an unsupported value")
        elif step.action == "wait":
            seconds = step.args.get("seconds")
            if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 0 < seconds <= 300:
                errors.append(f"{prefix}: seconds must be greater than 0 and at most 300")
        elif step.action == "app_launch":
            bundle_id = step.args.get("bundle_id")
            if not isinstance(bundle_id, str) or not bundle_id.strip():
                errors.append(f"{prefix}: app_launch needs a bundle_id")
        elif step.action == "scroll":
            dx, dy = step.args.get("dx", 0), step.args.get("dy", 0)
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (dx, dy)):
                errors.append(f"{prefix}: scroll dx and dy must be numbers")
            elif dx == 0 and dy == 0:
                errors.append(f"{prefix}: scroll dx and dy cannot both be zero")

    unknown = sorted(referenced - parameter_names)
    if unknown:
        errors.append(f"unknown parameter placeholder(s): {', '.join(unknown)}")
    if errors:
        raise SkillValidationError("invalid skill:\n- " + "\n- ".join(errors))
    return skill


def _placeholders(value: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(value))


def _valid_coordinates(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    )
