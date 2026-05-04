"""Unit tests for the recorder's coalescing logic. No live UI."""

from __future__ import annotations

from skill_forge.recorder.session import _TextBuffer, coalesce_keydown


def test_printable_chars_are_buffered():
    buf = _TextBuffer()
    action, payload = coalesce_keydown(buf, 1.0, "h", [])
    assert action == "buffer"
    assert payload is None
    coalesce_keydown(buf, 1.05, "i", [])
    assert buf.chars == ["h", "i"]
    assert buf.last_ts == 1.05


def test_shift_modifier_is_treated_as_printable():
    buf = _TextBuffer()
    action, _ = coalesce_keydown(buf, 1.0, "H", ["shift"])
    assert action == "buffer"
    assert buf.chars == ["H"]


def test_enter_flushes_buffer_and_emits_raw():
    buf = _TextBuffer()
    coalesce_keydown(buf, 1.0, "h", [])
    coalesce_keydown(buf, 1.05, "i", [])
    action, payload = coalesce_keydown(buf, 1.10, "\r", [])
    assert action == "flush"
    assert payload == {"chars": "\r", "modifiers": []}
    # Buffer is NOT reset by coalesce_keydown — the caller (worker) flushes it.
    assert buf.chars == ["h", "i"]


def test_cmd_modifier_is_not_buffered():
    buf = _TextBuffer()
    action, payload = coalesce_keydown(buf, 1.0, "a", ["cmd"])
    assert action == "raw"
    assert payload == {"chars": "a", "modifiers": ["cmd"]}
    assert buf.chars == []


def test_empty_chars_emits_raw_when_buffer_empty():
    buf = _TextBuffer()
    action, payload = coalesce_keydown(buf, 1.0, "", [])
    assert action == "raw"
    assert payload == {"chars": "", "modifiers": []}


def test_text_buffer_reset():
    buf = _TextBuffer(chars=["a", "b"], last_ts=1.0)
    buf.reset()
    assert buf.is_empty()
    assert buf.last_ts == 0.0
