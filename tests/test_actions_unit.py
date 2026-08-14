from __future__ import annotations

from types import SimpleNamespace

import pytest

from skill_forge.replay import actions


def test_focus_prefers_ax_focused(monkeypatch):
    elem = object()
    calls = []
    monkeypatch.setattr(actions, "find", lambda selector: elem)
    monkeypatch.setattr(
        actions,
        "AXUIElementSetAttributeValue",
        lambda target, attr, value: calls.append((target, attr, value)) or 0,
    )
    monkeypatch.setattr(actions, "click", lambda selector: pytest.fail("click fallback used"))

    actions.focus("AXApplication/AXTextField")

    assert calls == [(elem, "AXFocused", True)]


def test_focus_falls_back_to_click(monkeypatch):
    clicked = []
    monkeypatch.setattr(actions, "find", lambda selector: object())
    monkeypatch.setattr(actions, "AXUIElementSetAttributeValue", lambda *args: -1)
    monkeypatch.setattr(actions, "click", clicked.append)
    actions.focus("selector")
    assert clicked == ["selector"]


def test_scroll_posts_pixel_event(monkeypatch):
    event = object()
    posted = []
    monkeypatch.setattr(actions.Quartz, "CGEventCreateScrollWheelEvent", lambda *args: event)
    monkeypatch.setattr(
        actions.Quartz, "CGEventPost", lambda tap, value: posted.append((tap, value))
    )
    actions.scroll(dx=3, dy=-8)
    assert posted == [(actions.Quartz.kCGHIDEventTap, event)]


def test_read_is_allowlisted_and_can_strip(monkeypatch):
    elem = object()
    monkeypatch.setattr(actions, "find", lambda selector: elem)
    monkeypatch.setattr(actions, "get_attr", lambda target, attribute: "‎42‎")
    assert actions.read("selector", strip="‎") == "42"
    with pytest.raises(ValueError, match="unsupported"):
        actions.read("selector", attribute="AXChildren")


def test_app_launch_surfaces_open_failure(monkeypatch):
    monkeypatch.setattr(
        actions.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="not found", stdout=""),
    )
    with pytest.raises(RuntimeError, match="not found"):
        actions.app_launch("com.example.missing")


def test_click_coordinate_tuple_uses_coordinate_path(monkeypatch):
    calls = []
    monkeypatch.setattr(actions, "_coord_click", lambda x, y, button: calls.append((x, y, button)))
    actions.click((12.5, 30.0), button="right")
    assert calls == [(12.5, 30.0, "right")]
