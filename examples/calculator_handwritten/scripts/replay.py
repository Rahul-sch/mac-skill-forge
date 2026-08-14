"""Safe compatibility wrapper; ../skill.json is the source of truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_forge.replay.runner import run_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="calculator-add")
    parser.add_argument("--params", default="{}")
    args = parser.parse_args()
    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as exc:
        print(f"invalid --params JSON: {exc}", file=sys.stderr)
        return 2
    return run_manifest(Path(__file__).resolve().parents[1] / "skill.json", params)


if __name__ == "__main__":
    sys.exit(main())
