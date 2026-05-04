"""RecorderSession — orchestrates the recorder.

Architecture (do not collapse):

    main thread                  worker thread          capture thread     switch thread
    -----------                  -------------          --------------     -------------
    CFRunLoopRunInMode(0.2s)     pop queue              every Ns           every 250ms
       (CGEventTap callback         AX lookups            snap PNG           poll frontmost
        pushes (kind, ts, data)     selector_for          push frame         push app_switch
        to queue and returns)      snapshot_focused
                                    text-buffer flush
                                    write JSONL line

The fast/slow split is the entire point of phase 2 — DO NOT do AX lookups in
the event tap callback. The recorder dies (silently) if you do.
"""

from __future__ import annotations

import json
import logging
import platform
import queue
import signal
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import Quartz
from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCopyElementAtPosition,
    AXUIElementCreateSystemWide,
)

from skill_forge.recorder.ax_selector import selector_for
from skill_forge.recorder.ax_snapshot import snapshot_focused
from skill_forge.recorder.event_tap import install_tap
from skill_forge.recorder.screen_capture import every_n_seconds_loop
from skill_forge.utils.ax_helpers import get_attr
from skill_forge.utils.logging import setup_logging

log = logging.getLogger(__name__)

TEXT_FLUSH_IDLE_S = 1.5
APP_SWITCH_POLL_S = 0.25


@dataclass
class _TextBuffer:
    chars: list[str] = field(default_factory=list)
    last_ts: float = 0.0

    def is_empty(self) -> bool:
        return not self.chars

    def reset(self) -> None:
        self.chars = []
        self.last_ts = 0.0


def coalesce_keydown(
    buf: _TextBuffer, ts: float, chars: str, modifiers: list[str]
) -> tuple[str, dict[str, Any] | None]:
    """Pure helper: decide whether to buffer or emit a keydown.

    Returns (action, payload) where action is one of:
      "buffer"  -> chars appended to buf, no emit
      "flush"   -> buf flushed as text_input, then this keydown emitted as raw
      "raw"     -> buf was already empty; emit this keydown raw
    payload is the raw keydown dict for "flush"/"raw", else None.
    """
    is_printable = bool(chars) and chars.isprintable() and chars not in ("\r", "\n", "\t")
    non_shift_mods = [m for m in modifiers if m != "shift"]
    if is_printable and not non_shift_mods:
        buf.chars.append(chars)
        buf.last_ts = ts
        return "buffer", None
    payload = {"chars": chars, "modifiers": modifiers}
    if buf.is_empty():
        return "raw", payload
    return "flush", payload


class RecorderSession:
    def __init__(self, out_dir: Path, frame_interval: float = 2.0) -> None:
        self.out_dir = Path(out_dir)
        self.frames_dir = self.out_dir / "frames"
        self.trace_path = self.out_dir / "trace.jsonl"
        self.meta_path = self.out_dir / "meta.json"
        self.frame_interval = frame_interval

        self.queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.start_ts: float = 0.0
        self.end_ts: float = 0.0

        self._trace_fp: IO | None = None
        self._write_lock = threading.Lock()
        self._sysw = AXUIElementCreateSystemWide()
        self._text_buf = _TextBuffer()
        self._last_frontmost: str | None = None

    # ------------------------------------------------------------------ run

    def run(self) -> int:
        setup_logging()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.start_ts = time.time()
        self._trace_fp = self.trace_path.open("w", encoding="utf-8")

        prev_sigint = signal.signal(signal.SIGINT, lambda *_: self.stop_event.set())

        tap, _source = install_tap(self.queue)
        if tap is None:
            self._cleanup()
            print(
                "ERROR: CGEventTapCreate returned NULL. Grant Accessibility (and "
                "Input Monitoring if prompted) to Visual Studio Code - Insiders, "
                "restart it, then re-run."
            )
            signal.signal(signal.SIGINT, prev_sigint)
            return 1

        worker = threading.Thread(
            target=self._worker_loop, name="recorder-worker", daemon=True
        )
        capture = threading.Thread(
            target=every_n_seconds_loop,
            args=(self.frames_dir, self.frame_interval, self.stop_event, self._on_frame),
            name="recorder-capture",
            daemon=True,
        )
        switcher = threading.Thread(
            target=self._app_switch_loop, name="recorder-switch", daemon=True
        )
        worker.start()
        capture.start()
        switcher.start()

        log.info("Recording to %s — Ctrl-C to stop.", self.out_dir)
        try:
            while not self.stop_event.is_set():
                Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.2, True)
        except KeyboardInterrupt:
            self.stop_event.set()
        finally:
            signal.signal(signal.SIGINT, prev_sigint)

        log.info("Stopping; draining queue...")
        self.queue.put(None)  # sentinel
        worker.join(timeout=3.0)
        capture.join(timeout=3.0)
        switcher.join(timeout=2.0)

        self._flush_text_buffer(time.time())
        self.end_ts = time.time()
        self._cleanup()
        log.info("Session complete: %s", self.out_dir)
        return 0

    # -------------------------------------------------------------- worker

    def _worker_loop(self) -> None:
        while True:
            try:
                item = self.queue.get(timeout=0.5)
            except queue.Empty:
                if (
                    not self._text_buf.is_empty()
                    and (time.time() - self._text_buf.last_ts) > TEXT_FLUSH_IDLE_S
                ):
                    self._flush_text_buffer(time.time())
                if self.stop_event.is_set() and self.queue.empty():
                    return
                continue
            if item is None:
                return

            kind, ts, data = item

            if kind != "keydown" and not self._text_buf.is_empty():
                self._flush_text_buffer(ts)

            if kind == "click":
                self._handle_click(ts, data)
            elif kind == "keydown":
                self._handle_keydown(ts, data)
            elif kind == "scroll":
                self._write({"ts": ts, "type": "scroll", "data": data})
            elif kind == "app_switch":
                self._write({"ts": ts, "type": "app_switch", "data": data})
            elif kind == "frame":
                self._write({"ts": ts, "type": "frame", "data": data})

    def _handle_click(self, ts: float, data: dict[str, Any]) -> None:
        sel = self._selector_at_point(data["x"], data["y"])
        snap = snapshot_focused()
        self._write({"ts": ts, "type": "ax_snapshot", "data": snap})
        click_data = dict(data)
        click_data["ax_selector_at_point"] = sel
        self._write({"ts": ts, "type": "click", "data": click_data})

    def _handle_keydown(self, ts: float, data: dict[str, Any]) -> None:
        if self._is_secure_field_focused():
            if not self._text_buf.is_empty():
                self._flush_text_buffer(ts)
            return  # silently drop secret keystrokes

        action, payload = coalesce_keydown(
            self._text_buf, ts, data.get("chars", ""), data.get("modifiers", [])
        )
        if action == "buffer":
            return
        if action == "flush":
            self._flush_text_buffer(ts)
        # "raw" or "flush" both emit the raw keydown after any flush
        emit = {"keycode": data["keycode"]}
        if payload:
            emit.update(payload)
        self._write({"ts": ts, "type": "keydown", "data": emit})

    def _flush_text_buffer(self, _ts: float) -> None:
        if self._text_buf.is_empty():
            return
        text = "".join(self._text_buf.chars)
        self._write(
            {
                "ts": self._text_buf.last_ts,
                "type": "text_input",
                "data": {"text": text},
            }
        )
        self._text_buf.reset()

    def _selector_at_point(self, x: float, y: float) -> str | None:
        try:
            err, elem = AXUIElementCopyElementAtPosition(self._sysw, x, y, None)
        except Exception:
            return None
        if err != 0 or elem is None:
            return None
        return selector_for(elem) or None

    def _is_secure_field_focused(self) -> bool:
        focused_app = get_attr(self._sysw, "AXFocusedApplication")
        if focused_app is None:
            return False
        focused = get_attr(focused_app, "AXFocusedUIElement")
        if focused is None:
            return False
        return get_attr(focused, "AXSubrole") == "AXSecureTextField"

    # -------------------------------------------------------------- helpers

    def _on_frame(self, path: Path, ts: float) -> None:
        try:
            rel = str(path.relative_to(self.out_dir))
        except ValueError:
            rel = str(path)
        self.queue.put(("frame", ts, {"path": rel, "reason": "interval"}))

    def _app_switch_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                ws = NSWorkspace.sharedWorkspace()
                front = ws.frontmostApplication()
                bid = ""
                title = ""
                if front is not None and front.bundleIdentifier():
                    bid = str(front.bundleIdentifier())
                    title = str(front.localizedName() or "")
                if bid and bid != self._last_frontmost:
                    self.queue.put(
                        (
                            "app_switch",
                            time.time(),
                            {
                                "from_bundle": self._last_frontmost or "",
                                "to_bundle": bid,
                                "window_title": title,
                            },
                        )
                    )
                    self._last_frontmost = bid
            except Exception as e:
                log.debug("app_switch poll error: %r", e)
            self.stop_event.wait(APP_SWITCH_POLL_S)

    def _write(self, obj: dict[str, Any]) -> None:
        with self._write_lock:
            if self._trace_fp is None:
                return
            self._trace_fp.write(json.dumps(obj, default=str) + "\n")
            self._trace_fp.flush()

    def _cleanup(self) -> None:
        with self._write_lock:
            if self._trace_fp is not None:
                self._trace_fp.close()
                self._trace_fp = None
        meta = {
            "start_ts": self.start_ts,
            "end_ts": self.end_ts or time.time(),
            "macos_version": platform.mac_ver()[0],
            "hostname": socket.gethostname(),
        }
        self.meta_path.write_text(json.dumps(meta, indent=2))
