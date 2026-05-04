"""Capture a depth-bounded snapshot of the focused UI element."""

from __future__ import annotations

from typing import Any

from ApplicationServices import AXUIElementCreateSystemWide

from skill_forge.recorder.ax_selector import selector_for
from skill_forge.utils.ax_helpers import get_attr, get_children, get_role

_PARENT_DEPTH = 3
_CHILDREN_LIMIT = 10
_VALUE_TRUNCATE = 200

_INTERESTING_ATTRS: list[tuple[str, str]] = [
    ("AXIdentifier", "id"),
    ("AXTitle", "title"),
    ("AXValue", "value"),
    ("AXDescription", "desc"),
    ("AXSubrole", "subrole"),
]


def snapshot_focused() -> dict[str, Any]:
    """Return {selector, role, attrs, parent_chain[<=3], children[<=10]} for the focused element.

    Returns an empty-ish dict if no element is focused or AX permission isn't granted.
    """
    sysw = AXUIElementCreateSystemWide()
    focused_app = get_attr(sysw, "AXFocusedApplication")
    if focused_app is None:
        return _empty()
    focused = get_attr(focused_app, "AXFocusedUIElement") or focused_app

    return {
        "selector": selector_for(focused),
        "role": get_role(focused),
        "attrs": _collect_attrs(focused),
        "parent_chain": _walk_parents(focused, _PARENT_DEPTH),
        "children": _summarize_children(focused, _CHILDREN_LIMIT),
    }


def _empty() -> dict[str, Any]:
    return {
        "selector": None,
        "role": None,
        "attrs": {},
        "parent_chain": [],
        "children": [],
    }


def _collect_attrs(elem: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for ax_name, key in _INTERESTING_ATTRS:
        v = get_attr(elem, ax_name)
        if v is None:
            continue
        s = str(v)
        if not s:
            continue
        if len(s) > _VALUE_TRUNCATE:
            s = s[:_VALUE_TRUNCATE] + "..."
        out[key] = s
    return out


def _walk_parents(elem: Any, depth: int) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    cur = get_attr(elem, "AXParent")
    for _ in range(depth):
        if cur is None:
            break
        chain.append({"role": get_role(cur), "attrs": _collect_attrs(cur)})
        cur = get_attr(cur, "AXParent")
    return chain


def _summarize_children(elem: Any, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for child in get_children(elem)[:limit]:
        out.append({"role": get_role(child), "attrs": _collect_attrs(child)})
    return out
