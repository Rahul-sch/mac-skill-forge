"""Frozen schema for skills, steps, and parameters.

The action set is the contract between codify (Phase 3), the LLM pipeline
(Phase 5), and the replayer (Phase 4). Do NOT add new actions speculatively
("scroll", "drag", etc.) — expand only when a real workflow needs them.

The placeholder syntax in step args is `${param_name}`. Frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_ACTIONS: frozenset[str] = frozenset(
    {"click", "type", "press_key", "wait", "app_launch"}
)


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
