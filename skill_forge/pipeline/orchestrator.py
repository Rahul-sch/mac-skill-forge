"""Run the 4 stages in order and assemble a Skill.

The model identifier is hardcoded HERE and ONLY HERE. Originally targeted
`claude-sonnet-4-6` per the plan; switched to Groq's
`llama-3.3-70b-versatile` to work around Anthropic billing. Change this
single constant to swap models — do not sprinkle model strings across
stage modules.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from skill_forge.pipeline.schema import Parameter, Skill, Step, validate_skill
from skill_forge.pipeline.stages import abstractor, parameterizer, segmenter, validator

MODEL = "llama-3.3-70b-versatile"

log = logging.getLogger(__name__)


def build_skill(session_dir: Path, mock: bool = False, keep_debug: bool = False) -> Skill:
    if mock:
        return _mock_skill()

    session_dir = Path(session_dir)
    trace_path = session_dir / "trace.jsonl"
    if not trace_path.exists():
        raise FileNotFoundError(f"missing trace.jsonl in {session_dir}")

    raw = [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    # Drop frame events — text-only pipeline in v0 (vision is a v0.2 lever).
    events = [e for e in raw if e.get("type") != "frame"]
    if any(e.get("type") == "secure_input" for e in events):
        raise ValueError(
            "recording contains a redacted secure-field step; passwords and other "
            "secrets must be handled manually before this workflow can be built"
        )
    log.info("loaded %d events (%d after dropping frames)", len(raw), len(events))

    debug_dir = session_dir / "_pipeline_debug"
    if keep_debug:
        debug_dir.mkdir(exist_ok=True)
    model = os.environ.get("FORGE_MODEL", MODEL)

    log.info("[1/4] segmenter")
    segments = segmenter.run(events, model=model)
    _write_debug(debug_dir / "1_segments.json", segments, keep_debug)
    log.info("  -> %d segments", len(segments))

    log.info("[2/4] abstractor")
    raw_steps = abstractor.run(events, segments, model=model)
    _write_debug(debug_dir / "2_abstractor.json", raw_steps, keep_debug)
    log.info("  -> %d steps", len(raw_steps))

    log.info("[3/4] parameterizer")
    parameterized = parameterizer.run(raw_steps, model=model)
    _write_debug(debug_dir / "3_parameterizer.json", parameterized, keep_debug)
    log.info("  -> %d parameters", len(parameterized.get("parameters", [])))

    log.info("[4/4] validator")
    final = validator.run(parameterized, model=model)
    _write_debug(debug_dir / "4_validator.json", final, keep_debug)
    log.info(
        "  -> skill_name=%s, %d steps",
        final.get("skill_name"),
        len(final.get("steps", [])),
    )

    return validate_skill(_assemble(final))


def _write_debug(path: Path, value: object, enabled: bool) -> None:
    if enabled:
        path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _assemble(final: dict) -> Skill:
    return validate_skill(
        Skill(
            name=str(final["skill_name"]),
            description=str(final["skill_description"]),
            parameters=[
                Parameter(
                    name=str(p["name"]),
                    type=str(p.get("type", "string")),
                    description=str(p.get("description", "")),
                    default=None if p.get("default") is None else str(p["default"]),
                )
                for p in final.get("parameters", [])
            ],
            steps=[
                Step(
                    name=str(s["name"]),
                    action=str(s["action"]),
                    selector=s.get("selector"),
                    args=dict(s.get("args", {})),
                    assertions=list(s.get("assertions", [])),
                )
                for s in final.get("steps", [])
            ],
        )
    )


def _mock_skill() -> Skill:
    """Fixed Skill returned by --mock; bypasses all 4 LLM calls. Used in tests."""
    return Skill(
        name="mock-skill",
        description="A mocked skill used for testing the orchestrator.",
        parameters=[Parameter(name="x", type="string", description="example", default="hi")],
        steps=[
            Step(
                name="Launch app",
                action="app_launch",
                selector=None,
                args={"bundle_id": "com.example.app"},
                assertions=["app is frontmost"],
            )
        ],
    )
