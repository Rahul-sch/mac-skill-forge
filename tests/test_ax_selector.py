"""Pure-Python unit tests for the selector parser/serializer. No live AX UI."""

from __future__ import annotations

import pytest

from skill_forge.recorder.ax_selector import (
    Segment,
    parse_selector,
    serialize_segments,
)


def test_round_trip_calculator_button():
    s = (
        "AXApplication[bundle='com.apple.calculator']/"
        "AXWindow[title='Calculator']/"
        "AXButton[desc='eight']"
    )
    segs = parse_selector(s)
    assert [seg.role for seg in segs] == ["AXApplication", "AXWindow", "AXButton"]
    assert segs[0].attrs == {"bundle": "com.apple.calculator"}
    assert segs[1].attrs == {"title": "Calculator"}
    assert segs[2].attrs == {"desc": "eight"}
    assert serialize_segments(segs) == s


def test_round_trip_pos():
    s = "AXGroup[pos='0']/AXButton[pos='3']"
    assert serialize_segments(parse_selector(s)) == s


def test_role_only_segment():
    s = "AXWindow"
    segs = parse_selector(s)
    assert segs == [Segment(role="AXWindow", attrs={})]
    assert serialize_segments(segs) == s


def test_multiple_attrs_preserve_order():
    s = "AXButton[title='OK'; desc='confirm']"
    segs = parse_selector(s)
    assert list(segs[0].attrs.items()) == [("title", "OK"), ("desc", "confirm")]
    assert serialize_segments(segs) == s


def test_unquoted_value_is_tolerated():
    segs = parse_selector("AXGroup[pos=2]")
    assert segs[0].attrs == {"pos": "2"}


def test_empty_string_returns_no_segments():
    assert parse_selector("") == []
    assert serialize_segments([]) == ""


def test_bad_segment_raises():
    with pytest.raises(ValueError):
        parse_selector("not a role!")
