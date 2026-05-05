"""Selector resolution at replay time.

Wraps the Phase-1 find_by_selector with retry semantics and a structured
SelectorNotFound error that includes a Levenshtein-based suggestion. The
suggestion is best-effort: it walks the live AX tree of the app named by
the selector's first segment and finds the same-role element whose attrs
are closest to the missing leaf.
"""

from __future__ import annotations

from typing import Any

from AppKit import NSWorkspace
from ApplicationServices import AXUIElementCreateApplication

from skill_forge.recorder.ax_selector import (
    find_by_selector,
    parse_selector,
    selector_for,
)
from skill_forge.utils.ax_helpers import get_attr, get_children, get_role


class SelectorNotFound(RuntimeError):
    def __init__(
        self,
        selector: str,
        last_seen_app: str | None = None,
        suggested: str | None = None,
    ) -> None:
        self.selector = selector
        self.last_seen_app = last_seen_app
        self.suggested = suggested
        msg = f"selector not found: {selector}"
        if suggested:
            msg += f"\n  did you mean: {suggested}"
        if last_seen_app:
            msg += f"\n  (frontmost app: {last_seen_app})"
        super().__init__(msg)


def find(selector: str, timeout_s: float = 3.0) -> Any:
    """Resolve a selector to a live AXUIElement, raising SelectorNotFound on miss."""
    elem = find_by_selector(selector, timeout_s=timeout_s)
    if elem is not None:
        return elem
    raise SelectorNotFound(
        selector,
        last_seen_app=_frontmost_bundle(),
        suggested=_suggest_alternative(selector),
    )


def _frontmost_bundle() -> str | None:
    try:
        front = NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is not None and front.bundleIdentifier():
            return str(front.bundleIdentifier())
    except Exception:
        pass
    return None


def _suggest_alternative(selector: str) -> str | None:
    try:
        segs = parse_selector(selector)
    except ValueError:
        return None
    if not segs or segs[0].role != "AXApplication":
        return None
    bundle = segs[0].attrs.get("bundle")
    if not bundle:
        return None

    app_elem = _app_element_for_bundle(bundle)
    if app_elem is None:
        return None

    leaf = segs[-1]
    candidates = _walk_for_role(app_elem, leaf.role, max_depth=12)
    if not candidates:
        return None

    target_str = _attrs_signature(leaf.attrs)
    best = min(
        candidates,
        key=lambda c: _levenshtein(target_str, _attrs_signature(_collect_attrs(c))),
    )
    return selector_for(best)


def _app_element_for_bundle(bundle: str) -> Any | None:
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        bid = app.bundleIdentifier()
        if bid and str(bid) == bundle:
            return AXUIElementCreateApplication(app.processIdentifier())
    return None


def _walk_for_role(root: Any, role: str, max_depth: int = 12) -> list[Any]:
    out: list[Any] = []

    def walk(elem: Any, depth: int) -> None:
        if depth > max_depth:
            return
        if get_role(elem) == role:
            out.append(elem)
        for c in get_children(elem):
            walk(c, depth + 1)

    walk(root, 0)
    return out


def _collect_attrs(elem: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for ax_name, key in (
        ("AXIdentifier", "id"),
        ("AXTitle", "title"),
        ("AXValue", "value"),
        ("AXDescription", "desc"),
    ):
        v = get_attr(elem, ax_name)
        if v is None:
            continue
        s = str(v)
        if s:
            out[key] = s
    return out


def _attrs_signature(attrs: dict[str, str]) -> str:
    return "|".join(f"{k}={v}" for k, v in sorted(attrs.items()))


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            cur = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = cur
    return dp[n]
