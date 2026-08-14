from __future__ import annotations

from typer.testing import CliRunner

from skill_forge.cli import _agent_skill_root, app
from skill_forge.codify.manifest import manifest_to_json
from skill_forge.pipeline.schema import Parameter, Skill, Step

runner = CliRunner()


def _skill() -> Skill:
    return Skill(
        name="hello-test",
        description="Types a greeting.",
        parameters=[Parameter("name", "string", "person", "world")],
        steps=[Step("Wait briefly", "wait", None, {"seconds": 0.1}, [])],
    )


def test_replay_reports_invalid_json_without_traceback(tmp_path):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: x\n---\n")
    result = runner.invoke(app, ["replay", str(skill_dir), "--params", "not-json", "--dry-run"])
    assert result.exit_code == 2
    assert "invalid --params JSON" in result.output
    assert "Traceback" not in result.output


def test_agent_skill_roots_are_scoped_to_home(tmp_path):
    assert _agent_skill_root("codex", tmp_path) == tmp_path / ".codex" / "skills"
    assert _agent_skill_root("claude", tmp_path) == tmp_path / ".claude" / "skills"


def test_build_refuses_nonempty_output(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    result = runner.invoke(
        app,
        ["build", str(tmp_path / "unused"), "--out", str(output), "--mock"],
    )
    assert result.exit_code == 2
    assert "output directory is not empty" in result.output
    assert (output / "keep.txt").read_text() == "keep"


def test_manifest_fixture_is_valid(tmp_path):
    path = tmp_path / "skill.json"
    path.write_text(manifest_to_json(_skill()))
    assert path.exists()


def test_install_normalizes_to_safe_generated_files(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "skill.json").write_text(manifest_to_json(_skill()))
    (source / "SKILL.md").write_text("malicious instructions")
    (source / "evil.py").write_text("raise SystemExit('should not be copied')")
    install_root = tmp_path / "installed"
    monkeypatch.setattr("skill_forge.cli._agent_skill_root", lambda agent: install_root)

    result = runner.invoke(app, ["install", str(source), "--agent", "codex"])

    destination = install_root / "hello-test"
    assert result.exit_code == 0
    assert (destination / "skill.json").exists()
    assert (destination / "scripts" / "replay.py").exists()
    assert "malicious" not in (destination / "SKILL.md").read_text()
    assert not (destination / "evil.py").exists()
