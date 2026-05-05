"""Pipeline tests with a monkey-patched call_json — no API tokens spent in CI.

The orchestrator's job is to wire the four stages together and assemble a
Skill from the validator's output. Per-stage prompt quality is empirical
(verified by the Phase-5 live run); this file only proves the orchestration
shape is correct.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skill_forge.pipeline import claude_client, orchestrator
from skill_forge.pipeline.claude_client import _strip_fence
from skill_forge.pipeline.schema import VALID_ACTIONS, Skill

# --------------------------------------------------------- claude_client unit

def test_strip_fence_with_json_marker():
    assert _strip_fence("```json\n{\"a\":1}\n```") == '{"a":1}'


def test_strip_fence_no_fence():
    assert _strip_fence('{"a": 1}') == '{"a": 1}'


def test_strip_fence_bare_fence():
    assert _strip_fence("```\n[1,2,3]\n```") == "[1,2,3]"


def _make_fake_post(text: str):
    def fake_post(payload, timeout=60.0):
        return {"choices": [{"message": {"content": text}}]}
    return fake_post


def test_call_json_strips_fence(monkeypatch):
    monkeypatch.setattr(
        claude_client, "_post", _make_fake_post('```json\n{"ok": true}\n```')
    )
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    out = claude_client.call_json("sys", "user", model="m")
    assert out == {"ok": True}


def test_call_json_raises_bad_json_after_max_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_client, "_post", _make_fake_post("not json at all"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(claude_client.BadJSONFromModel):
        claude_client.call_json("sys", "user", model="m", max_attempts=2)
    assert (tmp_path / "last_failed_response.json").exists()


# -------------------------------------------------------- orchestrator wiring

def test_orchestrator_assembles_skill_from_canned_responses(monkeypatch, tmp_path):
    """Patch call_json with a per-stage queue and check the assembled Skill."""
    canned: list = [
        # 1. segmenter (returns wrapped object due to JSON mode)
        {"segments": [{"start_idx": 0, "end_idx": 3, "summary": "use calculator to add"}]},
        # 2. abstractor (also wrapped)
        {"steps": [
            {
                "name": "Launch Calculator",
                "action": "app_launch",
                "selector": None,
                "args": {"bundle_id": "com.apple.calculator"},
                "raw_event_indices": [0],
            },
            {
                "name": "Type first operand",
                "action": "type",
                "selector": None,
                "args": {"text": "2"},
                "raw_event_indices": [1],
            },
        ]},
        # 3. parameterizer
        {
            "parameters": [
                {
                    "name": "a",
                    "type": "number",
                    "description": "first operand",
                    "default": "2",
                }
            ],
            "steps": [
                {
                    "name": "Launch Calculator",
                    "action": "app_launch",
                    "selector": None,
                    "args": {"bundle_id": "com.apple.calculator"},
                },
                {
                    "name": "Type first operand",
                    "action": "type",
                    "selector": None,
                    "args": {"text": "${a}"},
                },
            ],
        },
        # 4. validator
        {
            "skill_name": "calculator-add-test",
            "skill_description": "Add a number using Calculator (test)",
            "parameters": [
                {
                    "name": "a",
                    "type": "number",
                    "description": "first operand",
                    "default": "2",
                }
            ],
            "steps": [
                {
                    "name": "Launch Calculator",
                    "action": "app_launch",
                    "selector": None,
                    "args": {"bundle_id": "com.apple.calculator"},
                    "assertions": ["Calculator is frontmost"],
                },
                {
                    "name": "Type first operand",
                    "action": "type",
                    "selector": None,
                    "args": {"text": "${a}"},
                    "assertions": ["The digit appears in input"],
                },
            ],
        },
    ]
    queue = list(canned)

    def fake_call_json(system, user, model, **kwargs):
        return queue.pop(0)

    monkeypatch.setattr(claude_client, "call_json", fake_call_json)

    session = tmp_path / "sess"
    session.mkdir()
    (session / "trace.jsonl").write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                {"ts": 1.0, "type": "app_switch", "data": {}},
                {"ts": 1.1, "type": "click", "data": {"ax_selector_at_point": "x"}},
                {"ts": 1.2, "type": "frame", "data": {}},  # filtered out
                {"ts": 1.3, "type": "click", "data": {"ax_selector_at_point": "y"}},
            ]
        )
    )

    skill = orchestrator.build_skill(session)
    assert isinstance(skill, Skill)
    assert skill.name == "calculator-add-test"
    assert [p.name for p in skill.parameters] == ["a"]
    assert skill.parameters[0].default == "2"
    assert [s.action for s in skill.steps] == ["app_launch", "type"]
    assert skill.steps[1].args == {"text": "${a}"}
    assert all(s.action in VALID_ACTIONS for s in skill.steps)
    assert queue == []  # all 4 stage calls consumed


def test_orchestrator_mock_bypasses_llm(tmp_path):
    """--mock returns the fixed mock skill without touching call_json."""
    skill = orchestrator.build_skill(tmp_path, mock=True)
    assert skill.name == "mock-skill"
    assert skill.parameters[0].name == "x"
    assert skill.steps[0].action == "app_launch"


def test_model_id_lives_in_one_place():
    """The active model id must appear in orchestrator.py only.

    A reference to the originally-planned `claude-sonnet-4-6` is allowed in
    the orchestrator's docstring (history); the active MODEL constant is
    what stages actually use.
    """
    import skill_forge.pipeline as pkg
    from skill_forge.pipeline.orchestrator import MODEL

    pkg_dir = Path(pkg.__file__).parent
    hits = []
    for py in pkg_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if MODEL in text:
            hits.append(py.name)
    assert hits == ["orchestrator.py"], (
        f"model id {MODEL!r} should only appear in orchestrator.py, found in: {hits}"
    )
