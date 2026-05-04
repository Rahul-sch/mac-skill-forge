"""Thin wrappers around the Accessibility (AX) C API.

All helpers tolerate missing attributes / dead refs by returning None
instead of raising — the AX tree is racy and we'd rather degrade than crash.
"""

from __future__ import annotations

from typing import Any

from AppKit import NSRunningApplication
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementGetPid,
)


def get_attr(elem: Any, name: str) -> Any:
    if elem is None:
        return None
    try:
        err, value = AXUIElementCopyAttributeValue(elem, name, None)
    except Exception:
        return None
    if err != 0:
        return None
    return value


def get_children(elem: Any) -> list:
    children = get_attr(elem, "AXChildren")
    if children is None:
        return []
    return list(children)


def get_role(elem: Any) -> str | None:
    role = get_attr(elem, "AXRole")
    return str(role) if role else None


def get_pid(elem: Any) -> int | None:
    if elem is None:
        return None
    try:
        err, pid = AXUIElementGetPid(elem, None)
    except Exception:
        return None
    if err != 0:
        return None
    return int(pid)


def bundle_id_for_pid(pid: int | None) -> str | None:
    if pid is None:
        return None
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app is None:
        return None
    bid = app.bundleIdentifier()
    return str(bid) if bid else None


def elements_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    if a is b:
        return True
    try:
        return bool(a.isEqualTo_(b))
    except Exception:
        return a == b
