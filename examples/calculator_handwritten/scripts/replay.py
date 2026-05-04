"""Hand-written replay for the calculator-add skill.

This is the Phase-3 fixture and the truth-test for Phase 4. The imports below
reference modules that ship in Phase 4 — until then this file is syntactically
valid Python that won't run.

Steps performed:
  1. Launch Calculator.
  2. Click All Clear to reset state.
  3. Click each digit of ${a} in turn.
  4. Click +.
  5. Click each digit of ${b} in turn.
  6. Click =.
  7. Read the result label and print it to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys

from skill_forge.replay.actions import app_launch, click, wait
from skill_forge.replay.ax_resolve import find

from skill_forge.utils.ax_helpers import get_attr

CALC_BUNDLE = "com.apple.calculator"

KEYPAD_BASE = (
    "AXApplication[bundle='com.apple.calculator']/"
    "AXWindow[id='main'; title='Calculator']/"
    "AXGroup[pos='0']/"
    "AXSplitGroup[id='main, SidebarNavigationSplitView']/"
    "AXGroup[pos='0']/"
    "AXGroup[id='CalculatorKeypadView']"
)

DIGIT_ID = {
    "0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
    "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine",
}


def button_selector(button_id: str) -> str:
    return f"{KEYPAD_BASE}/AXButton[id='{button_id}']"


RESULT_SELECTOR = (
    f"{KEYPAD_BASE}/AXGroup[pos='0']/"
    "AXScrollArea[id='StandardInputView'; desc='Input']/AXStaticText"
)


def click_digits(value: str) -> None:
    for ch in value:
        if ch not in DIGIT_ID:
            raise ValueError(f"non-digit character in operand: {ch!r}")
        click(button_selector(DIGIT_ID[ch]))
        wait(0.1)


def read_result() -> str:
    elem = find(RESULT_SELECTOR, timeout_s=2.0)
    if elem is None:
        raise RuntimeError(f"could not resolve result selector: {RESULT_SELECTOR}")
    raw = get_attr(elem, "AXValue")
    if raw is None:
        raise RuntimeError("result element has no AXValue")
    # Calculator wraps the displayed value in U+200E (LEFT-TO-RIGHT MARK).
    return str(raw).replace("‎", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="calculator-add")
    parser.add_argument("--params", required=True, help="JSON dict of parameters.")
    args = parser.parse_args()
    params = json.loads(args.params)
    for required in ("a", "b"):
        if required not in params:
            print(f"missing required parameter: {required}", file=sys.stderr)
            return 2

    a = str(params["a"])
    b = str(params["b"])

    app_launch(CALC_BUNDLE)
    wait(1.0)
    click(button_selector("AllClear"))
    wait(0.2)
    click_digits(a)
    click(button_selector("Add"))
    wait(0.1)
    click_digits(b)
    click(button_selector("Equals"))
    wait(0.4)
    print(read_result())
    return 0


if __name__ == "__main__":
    sys.exit(main())
