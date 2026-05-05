"""Parse a SKILL.md and run its scripts/replay.py as a subprocess.

Two non-obvious decisions:

1. Subprocess uses `sys.executable`, not bare `python`. This honors the
   active venv so the child can `import skill_forge.replay.actions`. If
   you run `forge replay` outside any venv but skill-forge is installed
   in the parent process, the child will inherit and it'll still work.

2. Frontmatter parsing is permissive (just `key: value` lines between the
   first two `---` markers — no full YAML), but parameter validation is
   strict: missing required params abort BEFORE the subprocess starts;
   extra params are warned about but ignored.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

_PARAM_LINE_RE = re.compile(
    r"^- `(\w+)`\s*\(([^,]+),\s*([^)]+)\):\s*(.*)$"
)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    fm: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    body = "\n".join(lines[end + 1 :])
    return fm, body


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
        m = _PARAM_LINE_RE.match(line)
        if not m:
            continue
        name, type_, qual, desc = m.groups()
        qual = qual.strip()
        out.append(
            {
                "name": name,
                "type": type_.strip(),
                "required": qual == "required",
                "default": None if qual == "required" else qual.removeprefix("default=").strip(),
                "description": desc.strip(),
            }
        )
    return out


def run_skill(skill_dir: Path, params: dict, dry_run: bool = False) -> int:
    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    replay_py = skill_dir / "scripts" / "replay.py"

    if not skill_md.exists():
        console.print(f"[red]ERROR[/red]: missing SKILL.md at {skill_md}")
        return 2
    if not replay_py.exists():
        console.print(f"[red]ERROR[/red]: missing scripts/replay.py at {replay_py}")
        return 2

    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    declared = parse_parameters(body)
    declared_names = {p["name"] for p in declared}
    required_names = {p["name"] for p in declared if p["required"]}

    missing = sorted(required_names - set(params.keys()))
    if missing:
        console.print(
            f"[red]ERROR[/red]: missing required parameter(s): {missing}"
        )
        return 2

    extras = sorted(set(params.keys()) - declared_names)
    if extras:
        console.print(
            f"[yellow]WARN[/yellow]: extra parameter(s) ignored: {extras}"
        )

    if dry_run:
        console.print(
            f"[cyan]dry-run[/cyan]: would run {replay_py} with params={params}"
        )
        return 0

    console.print(f"[cyan]replay[/cyan] {fm.get('name', skill_dir.name)} params={params}")
    cmd = [
        sys.executable,
        str(replay_py.resolve()),
        "--params",
        json.dumps(params),
    ]
    proc = subprocess.run(cmd, cwd=str(skill_dir.resolve()))
    return proc.returncode
