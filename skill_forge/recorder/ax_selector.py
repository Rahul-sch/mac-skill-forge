"""AX selector format: build, parse, and resolve selectors against the live UI tree.

Format (frozen):
    AXRole[attr1='value1'; attr2='value2']
joined by '/'. App-level segment uses bundle id:
    AXApplication[bundle='com.apple.calculator']

Attribute keys (in priority order, max 3 per segment):
    id    -> AXIdentifier
    title -> AXTitle
    value -> AXValue (only if str(value) <= 32 chars)
    desc  -> AXDescription
    pos   -> sibling index among same-role siblings (last resort)
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from AppKit import NSWorkspace
from ApplicationServices import AXUIElementCreateApplication

from skill_forge.utils.ax_helpers import (
    bundle_id_for_pid,
    elements_equal,
    get_attr,
    get_children,
    get_pid,
    get_role,
)

_KEY_TO_AX_ATTR: dict[str, tuple[str, int | None]] = {
    "id": ("AXIdentifier", None),
    "title": ("AXTitle", None),
    "value": ("AXValue", 32),
    "desc": ("AXDescription", None),
}

_SEGMENT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)(?:\[(.*)\])?$")


@dataclass
class Segment:
    role: str
    attrs: dict[str, str] = field(default_factory=dict)


def parse_selector(s: str) -> list[Segment]:
    segments: list[Segment] = []
    for raw in _split_unquoted(s, "/"):
        raw = raw.strip()
        if not raw:
            continue
        m = _SEGMENT_RE.match(raw)
        if not m:
            raise ValueError(f"bad selector segment: {raw!r}")
        role = m.group(1)
        attrs: dict[str, str] = {}
        attr_blob = m.group(2)
        if attr_blob:
            for pair in _split_unquoted(attr_blob, ";"):
                pair = pair.strip()
                if not pair:
                    continue
                key, _, value = pair.partition("=")
                key = key.strip()
                value = value.strip()
                if value.startswith("'") and value.endswith("'") and len(value) >= 2:
                    value = _unescape(value[1:-1])
                attrs[key] = value
        segments.append(Segment(role=role, attrs=attrs))
    return segments


def serialize_segments(segments: list[Segment]) -> str:
    parts = []
    for seg in segments:
        if seg.attrs:
            inner = "; ".join(f"{k}='{_escape(v)}'" for k, v in seg.attrs.items())
            parts.append(f"{seg.role}[{inner}]")
        else:
            parts.append(seg.role)
    return "/".join(parts)


def selector_for(elem: Any) -> str:
    """Walk parent chain from elem to root and emit a portable selector path."""
    if elem is None:
        return ""
    chain: list[Any] = []
    cur = elem
    seen = 0
    while cur is not None and seen < 50:
        chain.append(cur)
        parent = get_attr(cur, "AXParent")
        if parent is None or elements_equal(parent, cur):
            break
        cur = parent
        seen += 1
    chain.reverse()

    segments: list[Segment] = []
    parent = None
    for e in chain:
        role = get_role(e)
        if role is None:
            continue
        attrs = _attrs_for_segment(e, parent, role)
        segments.append(Segment(role=role, attrs=attrs))
        parent = e
    return serialize_segments(segments)


def _attrs_for_segment(elem: Any, parent: Any, role: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    if role == "AXApplication":
        pid = get_pid(elem)
        bundle = bundle_id_for_pid(pid)
        if bundle:
            attrs["bundle"] = bundle
        return attrs

    # Prefer one stable identifier over a brittle conjunction of every visible
    # value. Text-field values and document/window titles routinely change.
    for key in ("id", "desc", "title", "value"):
        ax_name, max_len = _KEY_TO_AX_ATTR[key]
        v = get_attr(elem, ax_name)
        if v is None:
            continue
        s = str(v)
        if not s:
            continue
        if max_len is not None and len(s) > max_len:
            continue
        attrs[key] = s
        break

    if not attrs and parent is not None:
        idx = _index_among_same_role_siblings(elem, parent, role)
        if idx is not None:
            attrs["pos"] = str(idx)
    return attrs


def _index_among_same_role_siblings(elem: Any, parent: Any, role: str) -> int | None:
    siblings = [c for c in get_children(parent) if get_role(c) == role]
    for i, c in enumerate(siblings):
        if elements_equal(c, elem):
            return i
    return None


def find_by_selector(selector: str, root: Any = None, timeout_s: float = 3.0) -> Any | None:
    """Resolve a selector to a live AXUIElement, polling until timeout."""
    segments = parse_selector(selector)
    if not segments:
        return None
    deadline = time.monotonic() + max(timeout_s, 0.0)
    while True:
        result = _try_find_once(segments, root)
        if result is not None:
            return result
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def _try_find_once(segments: list[Segment], root: Any) -> Any | None:
    if root is None:
        first = segments[0]
        if first.role != "AXApplication":
            return None
        bundle = first.attrs.get("bundle")
        if not bundle:
            return None
        app_elem = _app_element_for_bundle(bundle)
        if app_elem is None:
            return None
        result = _descend(app_elem, segments[1:])
        if result is not None:
            return result
        # App updates frequently insert/remove anonymous AXGroup containers.
        # Fall back to an exact leaf-attribute search within the same app.
        return _find_matching_descendant(app_elem, segments[-1], max_depth=16)
    return _descend(root, segments)


def _app_element_for_bundle(bundle: str) -> Any | None:
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        bid = app.bundleIdentifier()
        if bid and str(bid) == bundle:
            return AXUIElementCreateApplication(app.processIdentifier())
    return None


def _descend(elem: Any, segments: list[Segment]) -> Any | None:
    if not segments:
        return elem
    seg = segments[0]
    rest = segments[1:]
    children = get_children(elem)
    same_role = [c for c in children if get_role(c) == seg.role]

    if "pos" in seg.attrs:
        try:
            idx = int(seg.attrs["pos"])
        except ValueError:
            return None
        if 0 <= idx < len(same_role):
            return _descend(same_role[idx], rest)
        return None

    for child in same_role:
        if _matches_attrs(child, seg.attrs):
            result = _descend(child, rest)
            if result is not None:
                return result
    return None


def _matches_attrs(elem: Any, attrs: dict[str, str]) -> bool:
    for key, want in attrs.items():
        if key == "bundle":
            pid = get_pid(elem)
            got = bundle_id_for_pid(pid) or ""
        elif key in _KEY_TO_AX_ATTR:
            ax_name, _ = _KEY_TO_AX_ATTR[key]
            got = str(get_attr(elem, ax_name) or "")
        else:
            return False
        if got != want:
            return False
    return True


def _find_matching_descendant(root: Any, segment: Segment, max_depth: int) -> Any | None:
    stack: list[tuple[Any, int]] = [(root, 0)]
    visited = 0
    while stack and visited < 10_000:
        elem, depth = stack.pop()
        visited += 1
        if get_role(elem) == segment.role and _matches_attrs(elem, segment.attrs):
            return elem
        if depth < max_depth:
            stack.extend((child, depth + 1) for child in reversed(get_children(elem)))
    return None


def _split_unquoted(value: str, delimiter: str) -> list[str]:
    """Split selector syntax while preserving escaped delimiters in quotes."""
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char == "'":
            quoted = not quoted
        if char == delimiter and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if quoted:
        raise ValueError("unterminated quote in selector")
    parts.append("".join(current))
    return parts


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _unescape(value: str) -> str:
    out: list[str] = []
    escaped = False
    for char in value:
        if escaped:
            out.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            out.append(char)
    if escaped:
        out.append("\\")
    return "".join(out)
