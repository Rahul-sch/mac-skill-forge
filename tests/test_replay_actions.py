"""Unit tests for the replay layer that don't need a live UI.

The plan calls this file out as "skipped on CI; manual run only" — the live
end-to-end is in scripts/verify_phase4.py. The tests here cover pure logic:
runner frontmatter/parameter parsing and the Levenshtein helper used for
SelectorNotFound suggestions.
"""

from __future__ import annotations

from skill_forge.replay.ax_resolve import SelectorNotFound, _levenshtein
from skill_forge.replay.runner import parse_frontmatter, parse_parameters

CALC_MD = """\
---
name: calculator-add
description: Add two numbers
---

# calculator-add

Body text here.

## Parameters
- `a` (number, required): first operand
- `b` (number, required): second operand

## How to invoke
Run something.
"""

NO_FM = "no frontmatter here"

DEFAULTED_MD = """\
---
name: x
description: y
---

## Parameters
- `n` (number, default=42): with a default
- `s` (string, required): required string
"""


# ---------------------------------------------------------- frontmatter / params

def test_parse_frontmatter_basic():
    fm, body = parse_frontmatter(CALC_MD)
    assert fm == {"name": "calculator-add", "description": "Add two numbers"}
    assert body.startswith("\n# calculator-add")


def test_parse_frontmatter_missing():
    fm, body = parse_frontmatter(NO_FM)
    assert fm == {}
    assert body == NO_FM


def test_parse_parameters_basic():
    _, body = parse_frontmatter(CALC_MD)
    params = parse_parameters(body)
    assert [p["name"] for p in params] == ["a", "b"]
    assert all(p["required"] for p in params)
    assert params[0]["type"] == "number"
    assert params[0]["description"] == "first operand"


def test_parse_parameters_default():
    _, body = parse_frontmatter(DEFAULTED_MD)
    params = parse_parameters(body)
    by_name = {p["name"]: p for p in params}
    assert by_name["n"]["required"] is False
    assert by_name["n"]["default"] == "42"
    assert by_name["s"]["required"] is True
    assert by_name["s"]["default"] is None


def test_parse_parameters_ignores_other_sections():
    text = "## Steps\n- `not_a_param` (number, required): noise\n"
    assert parse_parameters(text) == []


# --------------------------------------------------------- Levenshtein helper

def test_levenshtein_basic():
    assert _levenshtein("", "") == 0
    assert _levenshtein("abc", "abc") == 0
    assert _levenshtein("abc", "abd") == 1
    assert _levenshtein("abc", "") == 3
    assert _levenshtein("", "abc") == 3
    assert _levenshtein("kitten", "sitting") == 3


def test_selector_not_found_message_includes_suggestion():
    err = SelectorNotFound(
        "AXButton[id='Wrong']",
        last_seen_app="com.apple.calculator",
        suggested="AXButton[id='Right']",
    )
    msg = str(err)
    assert "AXButton[id='Wrong']" in msg
    assert "did you mean" in msg
    assert "AXButton[id='Right']" in msg
    assert "com.apple.calculator" in msg
    assert err.selector == "AXButton[id='Wrong']"
    assert err.suggested == "AXButton[id='Right']"
