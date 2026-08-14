"""Validate and replay data-only skill manifests.

Generated skills execute through trusted Skill Forge action primitives. Legacy
``scripts/replay.py`` files are supported only with an explicit opt-in because
they are arbitrary Python programs running with the user's permissions.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from skill_forge.codify.manifest import load_manifest
from skill_forge.pipeline.schema import Parameter, Skill

console = Console()

_PARAM_LINE_RE = re.compile(r"^- `(\w+)`\s*\(([^,]+),\s*([^)]+)\):\s*(.*)$")
_PLACEHOLDER_RE = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text
    fm: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, "\n".join(lines[end + 1 :])


def parse_parameters(body: str) -> list[dict[str, object]]:
    in_section = False
    out: list[dict[str, object]] = []
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line.lower().startswith("## parameters")
            continue
        if not in_section:
            continue
        match = _PARAM_LINE_RE.match(line)
        if not match:
            continue
        name, type_, qualifier, description = match.groups()
        qualifier = qualifier.strip()
        out.append(
            {
                "name": name,
                "type": type_.strip(),
                "required": qualifier == "required",
                "default": (
                    None if qualifier == "required" else qualifier.removeprefix("default=").strip()
                ),
                "description": description.strip(),
            }
        )
    return out


def run_skill(
    skill_dir: Path,
    params: dict[str, Any],
    dry_run: bool = False,
    allow_script: bool = False,
) -> int:
    skill_dir = Path(skill_dir)
    manifest_path = skill_dir / "skill.json"
    skill_md = skill_dir / "SKILL.md"
    replay_py = skill_dir / "scripts" / "replay.py"

    if not skill_md.exists():
        console.print(f"[red]ERROR[/red]: missing SKILL.md at {skill_md}")
        return 2
    if manifest_path.exists():
        return run_manifest(manifest_path, params, dry_run=dry_run)
    if not replay_py.exists():
        console.print(f"[red]ERROR[/red]: missing skill.json and scripts/replay.py in {skill_dir}")
        return 2
    if not allow_script:
        console.print(
            "[red]ERROR[/red]: this is a legacy executable skill with no skill.json. "
            "Review scripts/replay.py, then re-run with --allow-script if you trust it."
        )
        return 2
    return _run_legacy_script(skill_md, replay_py, params, dry_run)


def run_manifest(manifest_path: Path, params: dict[str, Any], dry_run: bool = False) -> int:
    try:
        skill = load_manifest(manifest_path)
        resolved = resolve_params(skill, params)
    except (OSError, TypeError, ValueError) as exc:
        console.print(f"[red]ERROR[/red]: {exc}")
        return 2

    if dry_run:
        _print_plan(skill, resolved)
        return 0
    console.print(f"[cyan]replay[/cyan] {skill.name}")
    try:
        _execute(skill, resolved)
    except Exception as exc:  # noqa: BLE001 - present a clean CLI failure boundary.
        console.print(f"[red]FAILED[/red]: {exc}")
        return 1
    console.print("[green]complete[/green]")
    return 0


def resolve_params(skill: Skill, supplied: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(supplied, dict):
        raise TypeError("--params must decode to a JSON object")
    declared = {parameter.name: parameter for parameter in skill.parameters}
    extras = sorted(set(supplied) - set(declared))
    if extras:
        console.print(f"[yellow]WARN[/yellow]: extra parameter(s) ignored: {extras}")
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for parameter in skill.parameters:
        if parameter.name in supplied:
            raw = supplied[parameter.name]
        elif parameter.default is not None:
            raw = parameter.default
        else:
            missing.append(parameter.name)
            continue
        resolved[parameter.name] = _coerce_parameter(parameter, raw)
    if missing:
        raise ValueError(f"missing required parameter(s): {', '.join(sorted(missing))}")
    return resolved


def _coerce_parameter(parameter: Parameter, value: Any) -> Any:
    if parameter.type in {"string", "file"}:
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise TypeError(f"parameter {parameter.name!r} must be a string")
        return str(value)
    if parameter.type == "number":
        if isinstance(value, bool):
            raise TypeError(f"parameter {parameter.name!r} must be a number")
        if isinstance(value, (int, float)):
            return value
        try:
            number = float(str(value))
        except ValueError as exc:
            raise TypeError(f"parameter {parameter.name!r} must be a number") from exc
        return int(number) if number.is_integer() else number
    if parameter.type == "date":
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError as exc:
            raise TypeError(
                f"parameter {parameter.name!r} must be an ISO date (YYYY-MM-DD)"
            ) from exc
    raise TypeError(f"parameter {parameter.name!r} has unsupported type {parameter.type!r}")


def _subst(value: str, params: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        return str(params[match.group(1)])

    return _PLACEHOLDER_RE.sub(replace, value)


def _execute(skill: Skill, params: dict[str, Any]) -> None:
    from skill_forge.replay.actions import (
        app_launch,
        click,
        focus,
        press_key,
        read,
        scroll,
        type_text,
        wait,
        wait_for_app,
    )

    for index, step in enumerate(skill.steps, start=1):
        console.print(f"  [{index}/{len(skill.steps)}] {step.name}")
        args = {
            key: _subst(value, params) if isinstance(value, str) else value
            for key, value in step.args.items()
        }
        selector = _subst(step.selector, params) if step.selector else None
        if step.action == "app_launch":
            app_launch(args["bundle_id"])
            wait_for_app(args["bundle_id"])
        elif step.action == "wait":
            wait(float(args["seconds"]))
        elif step.action == "click":
            target: str | tuple[float, float]
            if selector:
                target = selector
            else:
                coords = args["coordinates"]
                target = (float(coords[0]), float(coords[1]))
            click(target, button=str(args.get("button", "left")))
        elif step.action == "type":
            if selector:
                focus(selector)
            type_text(str(args["text"]))
        elif step.action == "press_key":
            press_key(int(args["keycode"]), modifiers=args.get("modifiers", []))
        elif step.action == "scroll":
            if selector:
                focus(selector)
            scroll(float(args.get("dx", 0)), float(args.get("dy", 0)))
        elif step.action == "read":
            value = read(
                selector or "",
                attribute=str(args.get("attribute", "AXValue")),
                strip=str(args.get("strip", "")),
            )
            console.print(value)


def _print_plan(skill: Skill, params: dict[str, Any]) -> None:
    console.print(f"[cyan]validated dry-run[/cyan]: {skill.name}")
    if params:
        console.print(f"parameters={json.dumps(params, ensure_ascii=False)}")
    table = Table("#", "Action", "Step", "Target/details")
    for index, step in enumerate(skill.steps, start=1):
        selector = _subst(step.selector, params) if step.selector else ""
        args = {
            key: _subst(value, params) if isinstance(value, str) else value
            for key, value in step.args.items()
        }
        details = selector or json.dumps(args, ensure_ascii=False)
        table.add_row(str(index), step.action, step.name, Text(details))
    console.print(table)


def _run_legacy_script(
    skill_md: Path, replay_py: Path, params: dict[str, Any], dry_run: bool
) -> int:
    frontmatter, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    declared = parse_parameters(body)
    supplied = dict(params)
    missing: list[str] = []
    allowed: dict[str, Any] = {}
    for item in declared:
        name = str(item["name"])
        if name in supplied:
            allowed[name] = supplied[name]
        elif item["default"] is not None:
            allowed[name] = item["default"]
        elif item["required"]:
            missing.append(name)
    if missing:
        console.print(f"[red]ERROR[/red]: missing required parameter(s): {missing}")
        return 2
    if dry_run:
        console.print(
            f"[yellow]legacy dry-run[/yellow]: would execute reviewed Python {replay_py} "
            f"with params={allowed}"
        )
        return 0
    console.print(f"[yellow]legacy replay[/yellow] {frontmatter.get('name', skill_md.parent.name)}")
    proc = subprocess.run(
        [sys.executable, str(replay_py.resolve()), "--params", json.dumps(allowed)],
        cwd=str(skill_md.parent.resolve()),
    )
    return proc.returncode
