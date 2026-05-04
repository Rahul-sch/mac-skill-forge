"""CGEventTap installation and the FAST callback.

Hard rules (re-read before editing):
  1. The callback runs on the main run loop's thread for every input event.
     macOS kills taps whose callback takes longer than ~2ms.
  2. Therefore: NO AXUIElement* calls here, NO file I/O, NO synchronous Python
     work beyond extracting fields and pushing to the queue. The worker thread
     in session.py is the slow path — that's where AX lookups happen.
  3. The callback MUST return the event (or None to drop). Forgetting the
     return turns the Mac into molasses.
"""

from __future__ import annotations

import logging
import queue
import time
from typing import Any

import Quartz

log = logging.getLogger(__name__)

_BUTTON_FOR_TYPE = {
    Quartz.kCGEventLeftMouseDown: "left",
    Quartz.kCGEventRightMouseDown: "right",
    Quartz.kCGEventOtherMouseDown: "other",
}

_MOUSE_DOWN_TYPES = set(_BUTTON_FOR_TYPE.keys())


def event_mask() -> int:
    return (
        (1 << Quartz.kCGEventLeftMouseDown)
        | (1 << Quartz.kCGEventRightMouseDown)
        | (1 << Quartz.kCGEventOtherMouseDown)
        | (1 << Quartz.kCGEventKeyDown)
        | (1 << Quartz.kCGEventScrollWheel)
    )


def _flags_to_mods(flags: int) -> list[str]:
    mods: list[str] = []
    if flags & Quartz.kCGEventFlagMaskCommand:
        mods.append("cmd")
    if flags & Quartz.kCGEventFlagMaskShift:
        mods.append("shift")
    if flags & Quartz.kCGEventFlagMaskAlternate:
        mods.append("opt")
    if flags & Quartz.kCGEventFlagMaskControl:
        mods.append("ctrl")
    return mods


def make_callback(out_queue: queue.Queue):
    """Build a CGEventTap callback bound to a queue.

    Callback signature is (proxy, type_, event, refcon) -> event.
    Anything that takes longer than ~2ms must NOT live here.
    """

    def callback(proxy, type_, event, refcon):  # noqa: ARG001
        try:
            ts = time.time()
            if type_ in _MOUSE_DOWN_TYPES:
                point = Quartz.CGEventGetLocation(event)
                flags = Quartz.CGEventGetFlags(event)
                out_queue.put(
                    (
                        "click",
                        ts,
                        {
                            "x": float(point.x),
                            "y": float(point.y),
                            "button": _BUTTON_FOR_TYPE[type_],
                            "modifiers": _flags_to_mods(flags),
                        },
                    )
                )
            elif type_ == Quartz.kCGEventKeyDown:
                keycode = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode
                )
                flags = Quartz.CGEventGetFlags(event)
                chars = ""
                try:
                    actual, raw = Quartz.CGEventKeyboardGetUnicodeString(
                        event, 8, None, None
                    )
                    if raw:
                        chars = str(raw)
                except Exception:
                    chars = ""
                out_queue.put(
                    (
                        "keydown",
                        ts,
                        {
                            "keycode": int(keycode),
                            "chars": chars,
                            "modifiers": _flags_to_mods(flags),
                        },
                    )
                )
            elif type_ == Quartz.kCGEventScrollWheel:
                dy = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGScrollWheelEventDeltaAxis1
                )
                dx = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGScrollWheelEventDeltaAxis2
                )
                out_queue.put(("scroll", ts, {"dx": int(dx), "dy": int(dy)}))
        except Exception as e:
            # Never raise out of the callback — that would tear down the tap.
            log.debug("event_tap callback swallowed: %r", e)
        # CRITICAL: must return the event (or None to drop).
        return event

    return callback


def install_tap(out_queue: queue.Queue) -> tuple[Any, Any] | tuple[None, None]:
    """Create the CGEventTap and add it to the *current* run loop.

    Must be called from the main thread (where CFRunLoopRun will be invoked).
    Returns (tap, source) on success; (None, None) if macOS denied tap creation
    (typically because Input Monitoring / Accessibility isn't granted).
    """
    callback = make_callback(out_queue)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        event_mask(),
        callback,
        None,
    )
    if tap is None:
        return None, None
    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
    )
    Quartz.CGEventTapEnable(tap, True)
    return tap, source
