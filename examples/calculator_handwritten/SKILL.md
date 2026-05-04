---
name: calculator-add
description: Add two numbers using macOS Calculator and return the result
---

# calculator-add

Add ${a} and ${b} using the macOS Calculator app.

## Parameters
- `a` (number, required): first operand
- `b` (number, required): second operand

## How to invoke
Run: `python scripts/replay.py --params '{"a": 2, "b": 3}'`

## Steps (for reference; replay.py is the source of truth)
1. Launch Calculator (`AXApplication[bundle='com.apple.calculator']`)
2. Click `All Clear` to reset state
3. Click digits for `${a}`
4. Click `+`
5. Click digits for `${b}`
6. Click `=`
7. Read the result label and print it
