"""Skill Forge CLI: forge record / build / replay / doctor."""

from __future__ import annotations

import importlib
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import typer
from rich.console import Console
from rich.table import Table

from skill_forge.recorder.permissions import (
    accessibility_granted,
    input_monitoring_granted,
    screen_recording_granted,
)
from skill_forge.utils.logging import setup_logging

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Skill Forge — teach your Mac once; let any Claude agent replay it.",
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        from skill_forge import __version__

        console.print(f"skill-forge {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    pass


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
    required_ok = py_ok and mac_ok and pyobjc_ok

    if pyobjc_ok:
        ax_ok = accessibility_granted()
        input_ok = input_monitoring_granted()
        table.add_row(
            "Accessibility permission",
            _ok(ax_ok),
            "grant in System Settings → Privacy & Security → Accessibility" if not ax_ok else "",
        )
        table.add_row(
            "Input Monitoring permission",
            _ok(input_ok),
            "grant in System Settings → Privacy & Security → Input Monitoring"
            if not input_ok
            else "",
        )
        sr_ok = screen_recording_granted()
        table.add_row(
            "Screen Recording (optional)",
            "[green]AVAILABLE[/green]" if sr_ok else "[dim]OFF[/dim]",
            "only needed with forge record --capture-frames" if not sr_ok else "",
        )
        required_ok = required_ok and ax_ok and input_ok
    else:
        table.add_row("Accessibility permission", _ok(False), "PyObjC not available")
        table.add_row("Input Monitoring permission", _ok(False), "PyObjC not available")
        table.add_row("Screen Recording (optional)", "[dim]OFF[/dim]", "PyObjC not available")

    api_set = bool(os.environ.get("FORGE_API_KEY") or os.environ.get("GROQ_API_KEY"))
    detail = "API key set" if api_set else "export GROQ_API_KEY=gsk_..."
    table.add_row("LLM API key", _ok(api_set), detail)
    required_ok = required_ok and api_set

    httpx_ok, httpx_detail = _try_import("httpx")
    table.add_row("httpx (LLM client)", _ok(httpx_ok), httpx_detail)
    required_ok = required_ok and httpx_ok

    console.print(table)
    if not required_ok:
        raise typer.Exit(1)


@app.command()
def record(
    out: str = typer.Option(..., "--out", help="Session directory to write to."),
    frame_interval: float = typer.Option(
        2.0, "--frame-interval", help="Seconds between screenshots."
    ),
    capture_frames: bool = typer.Option(
        False,
        "--capture-frames",
        help="Save periodic full-screen frames for local review (off by default).",
    ),
) -> None:
    """Record a macOS demonstration to a session directory. Ctrl-C to stop."""
    from skill_forge.recorder.session import RecorderSession

    setup_logging()
    try:
        rc = RecorderSession(
            Path(out), frame_interval=frame_interval, capture_frames=capture_frames
        ).run()
    except (OSError, ValueError) as exc:
        console.print(f"[red]ERROR[/red]: {exc}")
        raise typer.Exit(2) from None
    raise typer.Exit(rc)


@app.command()
def build(
    session: str = typer.Argument(..., help="Path to a recorded session directory."),
    out: str = typer.Option(..., "--out", help="Where to write SKILL.md and scripts/replay.py."),
    mock: bool = typer.Option(False, "--mock", help="Bypass all LLM calls; emit a fixed Skill."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm sending trace data."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing output skill."),
    keep_debug: bool = typer.Option(
        False,
        "--keep-debug",
        help="Keep intermediate model responses in the session directory.",
    ),
) -> None:
    """Run the 4-stage Claude pipeline over a recorded session."""
    from skill_forge.codify.manifest import manifest_to_json
    from skill_forge.codify.replay_script import skill_to_replay_py
    from skill_forge.codify.skill_md import skill_to_md
    from skill_forge.pipeline.orchestrator import build_skill

    setup_logging()
    out_dir = Path(out)
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        console.print(f"[red]ERROR[/red]: output directory is not empty: {out_dir} (use --force)")
        raise typer.Exit(2)
    if not mock:
        trace_path = Path(session) / "trace.jsonl"
        if not trace_path.exists():
            console.print(f"[red]ERROR[/red]: missing trace.jsonl in {session}")
            raise typer.Exit(2)
        if not yes:
            host = urlparse(_llm_endpoint()).hostname or _llm_endpoint()
            console.print(
                "[yellow]Privacy notice[/yellow]: recorded typed text, selectors, and AX "
                f"snapshot values will be sent to {host}. Screen images are not uploaded."
            )
            if not typer.confirm("Continue?"):
                raise typer.Abort()
    try:
        skill_obj = build_skill(Path(session), mock=mock, keep_debug=keep_debug)
    except Exception as exc:  # noqa: BLE001 - CLI boundary for provider and schema errors.
        console.print(f"[red]ERROR[/red]: {exc}")
        raise typer.Exit(1) from None
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SKILL.md").write_text(skill_to_md(skill_obj), encoding="utf-8")
    (out_dir / "skill.json").write_text(manifest_to_json(skill_obj), encoding="utf-8")
    scripts_dir = out_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "replay.py").write_text(skill_to_replay_py(skill_obj), encoding="utf-8")
    console.print(f"[green]wrote[/green] {out_dir}/SKILL.md, skill.json, and scripts/replay.py")


@app.command(name="install")
def install_skill(
    skill: str = typer.Argument(..., help="Generated skill directory containing skill.json."),
    agent: str = typer.Option(..., "--agent", help="Target agent: codex or claude."),
    force: bool = typer.Option(False, "--force", help="Replace an existing installed skill."),
) -> None:
    """Install a validated generated skill for Codex or Claude."""
    from skill_forge.codify.manifest import load_manifest, manifest_to_json
    from skill_forge.codify.replay_script import skill_to_replay_py
    from skill_forge.codify.skill_md import skill_to_md

    source = Path(skill).resolve()
    try:
        manifest = load_manifest(source / "skill.json")
        root = _agent_skill_root(agent)
    except (OSError, ValueError) as exc:
        console.print(f"[red]ERROR[/red]: {exc}")
        raise typer.Exit(2) from None
    destination = root / manifest.name
    if destination.exists():
        if not force:
            console.print(f"[red]ERROR[/red]: already installed: {destination} (use --force)")
            raise typer.Exit(2)
        shutil.rmtree(destination)
    scripts_dir = destination / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (destination / "SKILL.md").write_text(skill_to_md(manifest), encoding="utf-8")
    (destination / "skill.json").write_text(manifest_to_json(manifest), encoding="utf-8")
    (scripts_dir / "replay.py").write_text(skill_to_replay_py(manifest), encoding="utf-8")
    console.print(f"[green]installed[/green] {manifest.name} → {destination}")


@app.command()
def replay(
    skill: str = typer.Argument(..., help="Path to a skill directory containing SKILL.md."),
    params: str = typer.Option("{}", "--params", help="JSON dict of parameters."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without launching."),
    allow_script: bool = typer.Option(
        False,
        "--allow-script",
        help="Allow a reviewed legacy skill to execute arbitrary scripts/replay.py.",
    ),
) -> None:
    """Replay a skill against the live UI."""
    import json as _json
    from pathlib import Path

    from skill_forge.replay.runner import run_skill

    setup_logging()
    try:
        parsed = _json.loads(params)
    except _json.JSONDecodeError as exc:
        console.print(f"[red]ERROR[/red]: invalid --params JSON: {exc}")
        raise typer.Exit(2) from None
    if not isinstance(parsed, dict):
        console.print("[red]ERROR[/red]: --params must decode to a JSON object")
        raise typer.Exit(2)
    rc = run_skill(Path(skill), parsed, dry_run=dry_run, allow_script=allow_script)
    raise typer.Exit(rc)


@app.command(name="eval")
def evaluate_skill(
    skill: str = typer.Argument(..., help="Generated skill directory to evaluate."),
    params: str = typer.Option("{}", "--params", help="JSON object of parameters."),
    runs: int = typer.Option(3, "--runs", min=1, max=100, help="Number of replay attempts."),
    delay: float = typer.Option(1.0, "--delay", min=0, help="Seconds between attempts."),
) -> None:
    """Replay a validated skill repeatedly and report its observed success rate."""
    from skill_forge.replay.runner import run_skill

    try:
        parsed = json.loads(params)
    except json.JSONDecodeError as exc:
        console.print(f"[red]ERROR[/red]: invalid --params JSON: {exc}")
        raise typer.Exit(2) from None
    if not isinstance(parsed, dict):
        console.print("[red]ERROR[/red]: --params must decode to a JSON object")
        raise typer.Exit(2)

    results: list[int] = []
    for attempt in range(1, runs + 1):
        console.rule(f"evaluation run {attempt}/{runs}")
        results.append(run_skill(Path(skill), parsed))
        if attempt < runs and delay:
            time.sleep(delay)
    passed = sum(code == 0 for code in results)
    console.print(f"success rate: [bold]{passed}/{runs} ({passed / runs:.0%})[/bold]")
    if passed != runs:
        raise typer.Exit(1)


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


def _llm_endpoint() -> str:
    from skill_forge.pipeline.claude_client import endpoint

    return endpoint()


def _agent_skill_root(agent: str, home: Path | None = None) -> Path:
    base = home or Path.home()
    normalized = agent.strip().lower()
    if normalized == "codex":
        return base / ".codex" / "skills"
    if normalized == "claude":
        return base / ".claude" / "skills"
    raise ValueError("--agent must be 'codex' or 'claude'")


if __name__ == "__main__":
    app()
