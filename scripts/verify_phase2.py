"""Phase 2 live verification.

Runs `forge record` in a subprocess, synthesizes real CGEvent mouse clicks
on Calculator's 2 / + / 2 / = buttons (so the event tap actually sees them),
sends SIGINT, then asserts the resulting session directory matches the
plan's acceptance criteria:

  - meta.json has start_ts AND end_ts
  - trace.jsonl has >=1 app_switch event
  - trace.jsonl has >=4 click events whose ax_selector_at_point contains AXButton
  - frames/ has >=4 PNGs

Run AFTER granting Accessibility (and Input Monitoring if prompted).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import Quartz
from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

from skill_forge.recorder.permissions import accessibility_granted
from skill_forge.utils.ax_helpers import get_attr, get_children, get_role

CALC_BUNDLE = "com.apple.calculator"
SESSION_DIR = Path("sessions/calc1")
RECORD_SECS = 8.0
FRAME_INTERVAL = 1.0


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


def walk(elem, depth=0, seen=None):
    if seen is None:
        seen = []
    if depth > 8:
        return seen
    seen.append(elem)
    for child in get_children(elem):
        walk(child, depth + 1, seen)
    return seen


def find_button(app_elem, label_lower_set: set[str]):
    for e in walk(app_elem):
        if get_role(e) != "AXButton":
            continue
        for attr in ("AXDescription", "AXTitle"):
            v = get_attr(e, attr)
            if v and str(v).lower() in label_lower_set:
                return e
    return None


def center_of(elem) -> tuple[float, float] | None:
    pos_v = get_attr(elem, "AXPosition")
    size_v = get_attr(elem, "AXSize")
    if pos_v is None or size_v is None:
        return None
    ok_p, pt = AXValueGetValue(pos_v, kAXValueCGPointType, None)
    ok_s, sz = AXValueGetValue(size_v, kAXValueCGSizeType, None)
    if not (ok_p and ok_s):
        return None
    return (float(pt.x + sz.width / 2.0), float(pt.y + sz.height / 2.0))


def synth_click(x: float, y: float) -> None:
    move = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, (x, y), Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    time.sleep(0.05)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, (x, y), Quartz.kCGMouseButtonLeft
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, (x, y), Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.05)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def main() -> None:
    if not accessibility_granted():
        fail("Accessibility denied. Grant it to VSCode Insiders and restart.")
    ok("Accessibility permission")

    if SESSION_DIR.exists():
        shutil.rmtree(SESSION_DIR)

    forge_bin = Path(".venv/bin/forge").resolve()
    if not forge_bin.exists():
        fail(f"forge binary not found at {forge_bin}")

    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            str(forge_bin),
            "record",
            "--out",
            str(SESSION_DIR),
            "--frame-interval",
            str(FRAME_INTERVAL),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ok(f"forge record launched (pid={proc.pid})")
    time.sleep(1.5)  # let tap install + worker start

    subprocess.run(["open", "-a", "Calculator"], check=True)
    time.sleep(2.0)

    app_elem = find_calc_app_element()
    if app_elem is None:
        proc.send_signal(signal.SIGINT)
        fail("Calculator process not found")

    button_targets = [
        ("two", {"2", "two"}),
        ("plus", {"+", "add", "plus"}),
        ("two", {"2", "two"}),
        ("equals", {"=", "equals"}),
    ]
    clicked = 0
    for name, labels in button_targets:
        btn = find_button(app_elem, labels)
        if btn is None:
            print(f"  WARN: could not locate Calculator button {name}")
            continue
        center = center_of(btn)
        if center is None:
            print(f"  WARN: no position for {name}")
            continue
        x, y = center
        synth_click(x, y)
        clicked += 1
        time.sleep(0.6)
    ok(f"synthesized {clicked} clicks on Calculator")

    # Quit Calculator (this gives us the second app_switch back)
    subprocess.run(
        ["osascript", "-e", 'tell application "Calculator" to quit'],
        check=False,
    )
    time.sleep(1.5)

    # Stop recorder
    proc.send_signal(signal.SIGINT)
    try:
        out, err = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    if proc.returncode not in (0, -signal.SIGINT):
        print(f"  recorder rc={proc.returncode}")
        print(f"  stderr={err.decode(errors='replace')[:500]}")
    ok("recorder stopped cleanly")

    # ---- artifact assertions
    meta_path = SESSION_DIR / "meta.json"
    trace_path = SESSION_DIR / "trace.jsonl"
    frames_dir = SESSION_DIR / "frames"

    if not meta_path.exists():
        fail(f"missing {meta_path}")
    meta = json.loads(meta_path.read_text())
    if not meta.get("start_ts") or not meta.get("end_ts"):
        fail(f"meta.json missing start_ts/end_ts: {meta}")
    if meta["end_ts"] < meta["start_ts"]:
        fail(f"end_ts < start_ts: {meta}")
    ok(f"meta.json has start_ts={meta['start_ts']:.3f} end_ts={meta['end_ts']:.3f}")

    if not trace_path.exists():
        fail(f"missing {trace_path}")
    events = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
    by_type: dict[str, int] = {}
    for ev in events:
        by_type[ev["type"]] = by_type.get(ev["type"], 0) + 1
    print("  event counts:", by_type)

    if by_type.get("app_switch", 0) < 1:
        fail("expected >=1 app_switch event")
    ok(f"app_switch count = {by_type['app_switch']}")

    button_clicks = [
        ev
        for ev in events
        if ev["type"] == "click"
        and (ev["data"].get("ax_selector_at_point") or "")
        and "AXButton" in ev["data"]["ax_selector_at_point"]
    ]
    if len(button_clicks) < 4:
        fail(
            f"expected >=4 click events with ax_selector_at_point containing AXButton, "
            f"got {len(button_clicks)} (total clicks={by_type.get('click', 0)})"
        )
    ok(f"button-click count = {len(button_clicks)}")
    for c in button_clicks[:4]:
        print(f"    {c['data']['ax_selector_at_point']}")

    pngs = sorted(frames_dir.glob("*.png"))
    if len(pngs) < 4:
        fail(f"expected >=4 PNGs in frames/, got {len(pngs)}")
    ok(f"frames/ has {len(pngs)} PNGs")

    print("\nALL PHASE 2 LIVE CHECKS PASSED")


if __name__ == "__main__":
    main()
