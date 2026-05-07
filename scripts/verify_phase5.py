"""Phase 5 live verification — the thesis test.

  1. Run `forge build sessions/calc1 --out examples/calculator_demo`
     (4 LLM calls; ~$0.02-0.10 in tokens).
  2. Diff the generated SKILL.md against the hand-written fixture (sanity
     report, not a hard pass/fail — names will differ).
  3. Run `forge replay examples/calculator_demo --params '{"a":7,"b":5}'`
     and assert stdout contains "12".

If step 3 fails, the iteration is in prompts (skill_forge/pipeline/prompts.py),
not code — see the Phase-5 picky-points discussion.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_DIR = Path("examples/calculator_demo")
HANDWRITTEN_DIR = Path("examples/calculator_handwritten")
SESSION_DIR = Path("sessions/calc1")
FORGE = Path(".venv/bin/forge").resolve()


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"PASS: {msg}")


def main() -> None:
    if not os.environ.get("GROQ_API_KEY"):
        fail("no LLM API key in env (set GROQ_API_KEY)")
    if not SESSION_DIR.exists():
        fail(f"missing session at {SESSION_DIR} — run scripts/verify_phase2.py first")

    if SKILL_DIR.exists():
        shutil.rmtree(SKILL_DIR)

    # ---- step 1: build
    print(f"=> forge build {SESSION_DIR} --out {SKILL_DIR}")
    t0 = time.time()
    proc = subprocess.run(
        [str(FORGE), "build", str(SESSION_DIR), "--out", str(SKILL_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    elapsed = time.time() - t0
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        fail(f"forge build returned {proc.returncode} after {elapsed:.1f}s")
    ok(f"forge build completed in {elapsed:.1f}s")

    skill_md = SKILL_DIR / "SKILL.md"
    replay_py = SKILL_DIR / "scripts" / "replay.py"
    if not skill_md.exists():
        fail(f"missing {skill_md}")
    if not replay_py.exists():
        fail(f"missing {replay_py}")
    ok(f"emitted {skill_md} ({skill_md.stat().st_size} B)")
    ok(f"emitted {replay_py} ({replay_py.stat().st_size} B)")

    # ---- step 2: diff against hand-written
    print("\n=> diff vs hand-written (sanity, not pass/fail)")
    a = (HANDWRITTEN_DIR / "SKILL.md").read_text().splitlines(keepends=True)
    b = skill_md.read_text().splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(a, b, fromfile="handwritten", tofile="generated"))
    print(diff or "(identical)")

    # Print the generated skill body so the user can read it
    print("\n=> generated SKILL.md:")
    print(skill_md.read_text())

    # ---- step 3: replay 7+5=12 and read Calculator's display via AX
    # (Auto-generated replay.py has no "read" action — that's intentional;
    # verification owns the assertion against the resulting world state.)
    subprocess.run(["killall", "Calculator"], check=False, capture_output=True)
    time.sleep(1.5)

    # Param names are LLM-chosen (a/b, num1/num2, ...). Read them in
    # declaration order from the generated SKILL.md and assign 7 -> first,
    # 5 -> second so the test is name-agnostic.
    from skill_forge.replay.runner import parse_frontmatter, parse_parameters
    text = skill_md.read_text()
    _fm, body = parse_frontmatter(text)
    declared = parse_parameters(body)
    if len(declared) < 2:
        fail(f"expected >=2 parameters in generated SKILL.md, got {len(declared)}")
    p_first, p_second = declared[0]["name"], declared[1]["name"]
    params = {p_first: 7, p_second: 5}
    print(f"=> forge replay calculator_demo --params {json.dumps(params)}")
    proc = subprocess.run(
        [str(FORGE), "replay", str(SKILL_DIR), "--params", json.dumps(params)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        fail(f"forge replay returned {proc.returncode}")
    ok("forge replay completed cleanly")

    time.sleep(0.5)  # let Calculator finish drawing
    result = _read_calculator_result()
    if result is None:
        fail("could not read Calculator's result display via AX")
    if result.strip() != "12":
        fail(f"Calculator displays {result!r}, expected '12'")
    ok(f"Calculator shows {result!r} — Skill Forge thesis validated")


def _read_calculator_result() -> str | None:
    from AppKit import NSWorkspace
    from ApplicationServices import AXUIElementCreateApplication

    from skill_forge.utils.ax_helpers import get_attr, get_children, get_role

    app_elem = None
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if str(app.bundleIdentifier() or "") == "com.apple.calculator":
            app_elem = AXUIElementCreateApplication(app.processIdentifier())
            break
    if app_elem is None:
        return None

    def walk(elem, depth=0, out=None):
        if out is None:
            out = []
        if depth > 12:
            return out
        out.append(elem)
        for c in get_children(elem):
            walk(c, depth + 1, out)
        return out

    # Calculator stores the displayed result in an AXStaticText inside an
    # AXScrollArea with id 'StandardInputView'.
    for e in walk(app_elem):
        if get_role(e) != "AXStaticText":
            continue
        parent = get_attr(e, "AXParent")
        if parent is None:
            continue
        if "StandardInputView" in str(get_attr(parent, "AXIdentifier") or ""):
            value = get_attr(e, "AXValue")
            if value is None:
                return None
            # Strip U+200E (LEFT-TO-RIGHT MARK) wrapper
            return str(value).replace("‎", "")
    return None


if __name__ == "__main__":
    main()
