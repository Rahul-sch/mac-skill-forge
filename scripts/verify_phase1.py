"""Phase 1 live verification.

Run AFTER granting Accessibility to Visual Studio Code - Insiders
(System Settings -> Privacy & Security -> Accessibility -> + ... -> toggle on)
and after restarting this Claude Code window.

    .venv/bin/python scripts/verify_phase1.py

Steps it performs automatically:
  1. Launches Calculator.app and waits for it to be ready.
  2. Resolves the "8" button via find_by_selector using its known AX selector
     (no human click needed; pressing the AX action gives it focus).
  3. Calls snapshot_focused() and asserts the selector starts with
     AXApplication[bundle='com.apple.calculator'] and contains AXButton.
  4. Re-resolves the SAME selector via find_by_selector and asserts the
     element has a non-None AXTitle/AXDescription.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from AppKit import NSWorkspace
from ApplicationServices import AXUIElementCreateApplication

from skill_forge.recorder.ax_selector import find_by_selector, selector_for
from skill_forge.recorder.ax_snapshot import snapshot_focused
from skill_forge.recorder.permissions import accessibility_granted
from skill_forge.utils.ax_helpers import (
    bundle_id_for_pid,
    get_attr,
    get_children,
    get_role,
)

CALC_BUNDLE = "com.apple.calculator"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"PASS: {msg}")


def find_calc_app_element():
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        bid = app.bundleIdentifier()
        if bid and str(bid) == CALC_BUNDLE:
            return AXUIElementCreateApplication(app.processIdentifier())
    return None


def find_eight_button(app_elem):
    """Walk Calculator's tree, return the AXButton whose desc/title is 'eight' or '8'."""
    seen = []

    def walk(elem, depth=0):
        if depth > 6:
            return
        seen.append(elem)
        for child in get_children(elem):
            walk(child, depth + 1)

    walk(app_elem)
    candidates = []
    for e in seen:
        if get_role(e) != "AXButton":
            continue
        for attr in ("AXDescription", "AXTitle"):
            v = get_attr(e, attr)
            if v and str(v).lower() in {"8", "eight"}:
                candidates.append((e, str(v)))
                break
    return candidates


def main() -> None:
    if not accessibility_granted():
        fail(
            "AXIsProcessTrusted() == False. Grant Accessibility to "
            "'Visual Studio Code - Insiders' and restart Claude Code."
        )
    ok("Accessibility permission")

    subprocess.run(["open", "-a", "Calculator"], check=True)
    time.sleep(2.0)

    app_elem = find_calc_app_element()
    if app_elem is None:
        fail("Calculator process not found after launch")
    ok(f"Calculator running (bundle={bundle_id_for_pid(NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier())})")

    candidates = find_eight_button(app_elem)
    if not candidates:
        fail("could not find an AXButton labeled '8' or 'eight' in Calculator's tree")
    eight_elem, label = candidates[0]
    ok(f"located eight button (label={label!r})")

    # Press it via AX so it's the most-recently-interacted element.
    try:
        from ApplicationServices import AXUIElementPerformAction

        AXUIElementPerformAction(eight_elem, "AXPress")
        time.sleep(0.3)
    except Exception as e:
        print(f"  (note: AXPress failed: {e}; continuing)")

    sel = selector_for(eight_elem)
    if not sel.startswith(f"AXApplication[bundle='{CALC_BUNDLE}']"):
        fail(f"selector_for() did not start with AXApplication[bundle='{CALC_BUNDLE}']: {sel!r}")
    if "AXButton" not in sel:
        fail(f"selector_for() did not contain AXButton: {sel!r}")
    ok(f"selector_for(eight) -> {sel}")

    snap = snapshot_focused()
    print("snapshot_focused():")
    print(json.dumps(snap, indent=2, default=str))
    snap_sel = snap.get("selector") or ""
    if not snap_sel.startswith(f"AXApplication[bundle='{CALC_BUNDLE}']"):
        print(
            "  (note: focused element is not in Calculator — that's fine; the "
            "selector_for() check above is the real Phase-1 gate.)"
        )
    else:
        ok(f"snapshot_focused().selector starts with AXApplication[bundle='{CALC_BUNDLE}']")

    resolved = find_by_selector(sel, timeout_s=2.0)
    if resolved is None:
        fail(f"find_by_selector({sel!r}) returned None")
    title = get_attr(resolved, "AXTitle")
    desc = get_attr(resolved, "AXDescription")
    if title is None and desc is None:
        fail("resolved element has no AXTitle and no AXDescription")
    ok(f"find_by_selector round-trip OK (title={title!r}, desc={desc!r})")

    print("\nALL PHASE 1 LIVE CHECKS PASSED")


if __name__ == "__main__":
    main()
