"""Skill Forge CLI: forge record / build / replay / doctor."""

from __future__ import annotations

import importlib
import os
import platform
import sys

import typer
from rich.console import Console
from rich.table import Table

from skill_forge.recorder.permissions import (
    accessibility_granted,
    screen_recording_granted,
)
from skill_forge.utils.logging import setup_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Skill Forge — teach your Mac once; let any Claude agent replay it.",
)
console = Console()


@app.command()
def doctor() -> None:
    """Check that the local environment is ready for record/build/replay."""
    setup_logging()
    table = Table(title="forge doctor", show_lines=False)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    py_ok = sys.version_info >= (3, 11)
    table.add_row(
        "Python ≥ 3.11",
        _ok(py_ok),
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )

    mac_ver = platform.mac_ver()[0] or "unknown"
    mac_ok = _mac_at_least(mac_ver, 14)
    table.add_row("macOS ≥ 14", _ok(mac_ok), mac_ver)

    pyobjc_ok, pyobjc_detail = _try_import("Quartz")
    table.add_row("PyObjC importable", _ok(pyobjc_ok), pyobjc_detail)

    if pyobjc_ok:
        ax_ok = accessibility_granted()
        table.add_row(
            "Accessibility permission",
            _ok(ax_ok),
            "grant in System Settings → Privacy & Security → Accessibility" if not ax_ok else "",
        )
        sr_ok = screen_recording_granted()
        table.add_row(
            "Screen Recording permission",
            _ok(sr_ok),
            "grant in System Settings → Privacy & Security → Screen Recording" if not sr_ok else "",
        )
    else:
        table.add_row("Accessibility permission", _ok(False), "PyObjC not available")
        table.add_row("Screen Recording permission", _ok(False), "PyObjC not available")

    groq_set = bool(os.environ.get("GROQ_API_KEY"))
    anth_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    key_set = groq_set or anth_set
    detail = "GROQ_API_KEY set" if groq_set else (
        "ANTHROPIC_API_KEY set" if anth_set else "export GROQ_API_KEY=... or ANTHROPIC_API_KEY=..."
    )
    table.add_row("LLM API key", _ok(key_set), detail)

    httpx_ok, httpx_detail = _try_import("httpx")
    table.add_row("httpx (LLM client)", _ok(httpx_ok), httpx_detail)

    console.print(table)


@app.command()
def record(
    out: str = typer.Option(..., "--out", help="Session directory to write to."),
    frame_interval: float = typer.Option(
        2.0, "--frame-interval", help="Seconds between screenshots."
    ),
) -> None:
    """Record a macOS demonstration to a session directory. Ctrl-C to stop."""
    from pathlib import Path

    from skill_forge.recorder.session import RecorderSession

    setup_logging()
    rc = RecorderSession(Path(out), frame_interval=frame_interval).run()
    raise typer.Exit(rc)


@app.command()
def build(
    session: str = typer.Argument(..., help="Path to a recorded session directory."),
    out: str = typer.Option(..., "--out", help="Where to write SKILL.md and scripts/replay.py."),
    mock: bool = typer.Option(False, "--mock", help="Bypass all LLM calls; emit a fixed Skill."),
) -> None:
    """Run the 4-stage Claude pipeline over a recorded session."""
    from pathlib import Path

    from skill_forge.codify.replay_script import skill_to_replay_py
    from skill_forge.codify.skill_md import skill_to_md
    from skill_forge.pipeline.orchestrator import build_skill

    setup_logging()
    skill = build_skill(Path(session), mock=mock)
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SKILL.md").write_text(skill_to_md(skill), encoding="utf-8")
    scripts_dir = out_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "replay.py").write_text(skill_to_replay_py(skill), encoding="utf-8")
    console.print(f"[green]wrote[/green] {out_dir}/SKILL.md and scripts/replay.py")


@app.command()
def replay(
    skill: str = typer.Argument(..., help="Path to a skill directory containing SKILL.md."),
    params: str = typer.Option("{}", "--params", help="JSON dict of parameters."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without launching."),
) -> None:
    """Replay a skill against the live UI."""
    import json as _json
    from pathlib import Path

    from skill_forge.replay.runner import run_skill

    setup_logging()
    rc = run_skill(Path(skill), _json.loads(params), dry_run=dry_run)
    raise typer.Exit(rc)


@app.command(name="_devsnap", hidden=True)
def _devsnap() -> None:
    """Hidden: print snapshot_focused() as JSON for the currently focused element."""
    import json

    from skill_forge.recorder.ax_snapshot import snapshot_focused

    snap = snapshot_focused()
    print(json.dumps(snap, indent=2, default=str))


def _ok(ok: bool) -> str:
    return "[green]PASS[/green]" if ok else "[red]FAIL[/red]"


def _try_import(name: str) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(name)
        return True, getattr(mod, "__version__", "ok")
    except ImportError as e:
        return False, str(e)


def _mac_at_least(ver: str, major: int) -> bool:
    try:
        return int(ver.split(".")[0]) >= major
    except (ValueError, IndexError):
        return False


def _not_implemented(cmd: str, **kwargs: object) -> int:
    console.print(f"[yellow]forge {cmd}[/yellow] is not implemented yet (args: {kwargs}).")
    return 1


if __name__ == "__main__":
    app()
