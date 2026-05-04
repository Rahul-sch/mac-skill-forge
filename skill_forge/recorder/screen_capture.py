"""Periodic screenshot capture. Runs in its own thread; pushes frame events
back to the recorder via an on_frame callback (the worker writes them to
trace.jsonl, keeping all JSONL writes serialized through one thread)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import Quartz
from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep


def screen_locked() -> bool:
    """True if the screen is locked / screensaver active. Best-effort."""
    try:
        d = Quartz.CGSessionCopyCurrentDictionary()
        if d is None:
            return False
        return bool(d.get("CGSSessionScreenIsLocked", False))
    except Exception:
        return False


def capture_main_display(out_path: Path) -> bool:
    main_id = Quartz.CGMainDisplayID()
    image = Quartz.CGDisplayCreateImage(main_id)
    if image is None:
        return False
    bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
    if bitmap is None:
        return False
    data = bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    if data is None:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return bool(data.writeToFile_atomically_(str(out_path), True))


def every_n_seconds_loop(
    out_dir: Path,
    interval: float,
    stop_event: threading.Event,
    on_frame: Callable[[Path, float], None],
) -> None:
    """Capture the main display every `interval` seconds until stop_event is set.

    Skips capture while the screen is locked. Calls on_frame(path, ts) after
    each successful capture so the worker can record a frame event.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    counter = 0
    while not stop_event.is_set():
        if not screen_locked():
            counter += 1
            path = out_dir / f"{counter:04d}.png"
            ts = time.time()
            if capture_main_display(path):
                try:
                    on_frame(path, ts)
                except Exception:
                    pass
        stop_event.wait(interval)
