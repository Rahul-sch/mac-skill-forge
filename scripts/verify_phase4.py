"""Phase 4 live verification.

Runs the calculator-add skill three times via `forge replay`:
  1. {a:7, b:5}   -> expect 12
  2. {a:12, b:30} -> expect 42
  3. {a:7, b:5}   -> expect 12 (regression: proves no state leaks between runs)

Then exercises the SelectorNotFound suggestion path with a deliberately
broken Calculator selector and asserts the Levenshtein hint is non-empty
and reasonable.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from skill_forge.recorder.permissions import accessibility_granted
from skill_forge.replay.ax_resolve import SelectorNotFound, find

SKILL_DIR = Path("examples/calculator_handwritten")
FORGE = Path(".venv/bin/forge").resolve()


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"PASS: {msg}")


def run_one(params: dict, expected: str) -> None:
    t0 = time.time()
    proc = subprocess.run(
        [str(FORGE), "replay", str(SKILL_DIR), "--params", json.dumps(params)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        fail(f"forge replay returned {proc.returncode} for params={params}")
    # The hand-written replay prints the result on its own line. The runner also
    # prints a "replay calculator-add params=..." status line. Find the result.
    candidates = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    result = None
    for line in reversed(candidates):
        if line == expected:
            result = line
            break
    if result is None:
        print(proc.stdout)
        fail(f"expected {expected!r} in stdout, got lines={candidates}")
    ok(f"params={params} -> {result} (in {elapsed:.2f}s)")


def test_selector_not_found_suggestion() -> None:
    # Calculator must be running for the suggestion lookup to walk its tree.
    subprocess.run(["open", "-b", "com.apple.calculator"], check=True)
    time.sleep(1.0)

    bad = (
        "AXApplication[bundle='com.apple.calculator']/"
        "AXWindow[id='main'; title='Calculator']/"
        "AXGroup[pos='0']/"
        "AXSplitGroup[id='main, SidebarNavigationSplitView']/"
        "AXGroup[pos='0']/"
        "AXGroup[id='CalculatorKeypadView']/"
        "AXButton[id='Twelve']"  # deliberately wrong
    )
    try:
        find(bad, timeout_s=0.5)
    except SelectorNotFound as e:
        if not e.suggested:
            fail("SelectorNotFound has no suggestion")
        if "AXButton" not in e.suggested:
            fail(f"suggestion did not name an AXButton: {e.suggested}")
        ok(f"bad selector -> SelectorNotFound, suggestion: {e.suggested}")
        return
    fail("expected SelectorNotFound but find() returned successfully")


def main() -> None:
    if not accessibility_granted():
        fail("Accessibility denied")
    if not FORGE.exists():
        fail(f"forge binary not found at {FORGE}")

    # Make sure calculator is in a clean state — quit any existing instance.
    subprocess.run(
        ["osascript", "-e", 'tell application "Calculator" to quit'],
        check=False,
    )
    time.sleep(0.5)

    run_one({"a": 7, "b": 5}, "12")
    run_one({"a": 12, "b": 30}, "42")
    run_one({"a": 7, "b": 5}, "12")
    test_selector_not_found_suggestion()
    print("\nALL PHASE 4 LIVE CHECKS PASSED")


if __name__ == "__main__":
    main()
