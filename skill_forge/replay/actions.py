"""Replay primitives: click, type_text, press_key, app_launch, wait, wait_for.

Synchronous and blocking by design — easy to debug, easy to step through.
DO NOT make these async.

click() prefers AXUIElementPerformAction(elem, "AXPress") because it is
faster, doesn't move the cursor, and survives if the window moves between
selector resolution and the click. Falls back to a CGEventPost coordinate
click computed from AXPosition + AXSize when AXPress is unavailable or
returns an error.
"""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Sequence
from typing import Any

import Quartz
from ApplicationServices import (
    AXUIElementPerformAction,
    AXValueGetValue,
    kAXValueCGPointType,
    kAXValueCGSizeType,
)

from skill_forge.replay.ax_resolve import find
from skill_forge.utils.ax_helpers import get_attr

log = logging.getLogger(__name__)

_INTER_KEY_SLEEP_S = 0.01

_MOD_FLAG: dict[str, int] = {
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "opt": Quartz.kCGEventFlagMaskAlternate,
    "ctrl": Quartz.kCGEventFlagMaskControl,
}


def click(target: str | tuple[float, float], button: str = "left") -> None:
    """Click `target` (an AX selector string or an (x, y) tuple).

    Prefer AXPress on the resolved element; fall back to a coordinate click.
    """
    if isinstance(target, tuple):
        x, y = target
        _coord_click(x, y, button)
        return

    elem = find(target)
    if _try_axpress(elem):
        return
    center = _center_of(elem)
    if center is None:
        raise RuntimeError(
            f"click({target!r}): element supports neither AXPress nor "
            "AXPosition+AXSize; cannot click"
        )
    x, y = center
    _coord_click(x, y, button)


def _try_axpress(elem: Any) -> bool:
    actions = get_attr(elem, "AXActions") or []
    if "AXPress" not in actions:
        return False
    try:
        err = AXUIElementPerformAction(elem, "AXPress")
    except Exception as e:
        log.debug("AXPress raised %r; falling back to coord", e)
        return False
    if err != 0:
        log.debug("AXPress returned err=%d; falling back to coord", err)
        return False
    return True


def _center_of(elem: Any) -> tuple[float, float] | None:
    pos_v = get_attr(elem, "AXPosition")
    size_v = get_attr(elem, "AXSize")
    if pos_v is None or size_v is None:
        return None
    ok_p, pt = AXValueGetValue(pos_v, kAXValueCGPointType, None)
    ok_s, sz = AXValueGetValue(size_v, kAXValueCGSizeType, None)
    if not (ok_p and ok_s):
        return None
    return (float(pt.x + sz.width / 2.0), float(pt.y + sz.height / 2.0))


def _coord_click(x: float, y: float, button: str) -> None:
    if button == "right":
        btn = Quartz.kCGMouseButtonRight
        down_t, up_t = Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp
    else:
        btn = Quartz.kCGMouseButtonLeft
        down_t, up_t = Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp

    move = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x, y), btn)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
    time.sleep(0.02)
    down = Quartz.CGEventCreateMouseEvent(None, down_t, (x, y), btn)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    time.sleep(0.02)
    up = Quartz.CGEventCreateMouseEvent(None, up_t, (x, y), btn)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def type_text(text: str) -> None:
    """Type each character via CGEventKeyboardSetUnicodeString.

    One down/up pair per char with a 10ms inter-key sleep so receivers see
    distinct events rather than a coalesced burst.

    Explicitly clears modifier flags on every event — CGEventCreateKeyboardEvent
    with source=None inherits the current modifier state, so a recent cmd+N
    leaks "cmd" onto subsequent typed chars.
    """
    for ch in text:
        ev_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventSetFlags(ev_down, 0)
        Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
        ev_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventSetFlags(ev_up, 0)
        Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
        time.sleep(_INTER_KEY_SLEEP_S)


def press_key(keycode: int, modifiers: Sequence[str] = ()) -> None:
    flags = 0
    for m in modifiers:
        flags |= _MOD_FLAG.get(m, 0)
    ev_down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    if flags:
        Quartz.CGEventSetFlags(ev_down, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
    ev_up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    if flags:
        Quartz.CGEventSetFlags(ev_up, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)


def app_launch(bundle_id: str) -> None:
    """Launch (or activate) an app by bundle id. Uses `open -b` for reliability."""
    proc = subprocess.run(
        ["open", "-b", bundle_id],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"app_launch({bundle_id!r}) failed: {proc.stderr.strip() or proc.stdout.strip()}"
        )


def wait(seconds: float) -> None:
    time.sleep(max(0.0, float(seconds)))


def wait_for(selector: str, timeout: float = 5.0) -> Any:
    """Poll find_by_selector until it resolves or `timeout` elapses (raises on miss).

    Used after every app_launch — the window-not-yet-created race is the most
    common cause of replay flakes.
    """
    return find(selector, timeout_s=timeout)
