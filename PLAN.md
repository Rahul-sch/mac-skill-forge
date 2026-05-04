# Skill Forge — Claude Code Build Plan

## How to use this file with Claude Code

- `mkdir skill-forge && cd skill-forge && git init`
- Save this file as `PLAN.md` at the project root.
- In Claude Code, run: `read PLAN.md and execute Phase 0`. After each phase finishes, review, commit, and say `execute Phase N+1`. Do NOT let Claude Code skip phases or merge them — each phase is gated on a concrete acceptance test.

The phases are ordered so that deterministic pieces are validated before the LLM pipeline is introduced. This is non-negotiable. If the recorder and replayer don't work end-to-end on a hand-written skill, no amount of prompt engineering will save you.

---

## 0. Constants and conventions

- **Language:** Python 3.11+
- **OS:** macOS 14+ (Apple Silicon). Mac-only for v0. Do NOT add Linux/Windows scaffolding.
- **Package manager:** `uv` (preferred) or `pip + venv`. Use a virtualenv.
- **License:** MIT.
- **API key:** read from `ANTHROPIC_API_KEY` env var. Never commit. `.env.example` only.
- **Claude model:** `claude-sonnet-4-6` for the pipeline. Don't hardcode anywhere except `skill_forge/pipeline/orchestrator.py`.
- **Style:** keep the v0 code under ~1500 LOC total. Resist the urge to over-engineer. No abstract base classes for things that have one implementation. No LangChain. No LangGraph. No Pydantic v2 models for things that can be dataclass.
- **Logging:** use stdlib `logging`, configured once in `skill_forge/utils/logging.py`. No `print` outside the CLI entrypoint.
- **Commit policy:** one commit per phase, message format `phase N: <summary>`. Verify the acceptance test passes before committing.

---

## 1. Final project structure (you will build toward this)

```
skill-forge/
├── PLAN.md                          ← this file
├── README.md                        ← Phase 7
├── LICENSE                          ← MIT, Phase 0
├── pyproject.toml                   ← Phase 0
├── .gitignore                       ← Phase 0
├── .env.example                     ← Phase 0
├── skill_forge/
│   ├── __init__.py
│   ├── __main__.py                  ← `python -m skill_forge` dispatcher
│   ├── cli.py                       ← Typer app: record / build / replay / doctor
│   ├── recorder/
│   │   ├── __init__.py
│   │   ├── permissions.py           ← AXIsProcessTrusted + Screen Recording check
│   │   ├── ax_snapshot.py           ← snapshot focused element + window subtree
│   │   ├── ax_selector.py           ← turn an AXUIElement into a portable selector string
│   │   ├── event_tap.py             ← CGEventTap → JSONL events
│   │   ├── screen_capture.py        ← CGWindowListCreateImage → PNG
│   │   └── session.py               ← session dir, JSONL writer, run loop
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py          ← run all 4 stages in order
│   │   ├── claude_client.py         ← thin wrapper over `anthropic` SDK
│   │   ├── prompts.py               ← all 4 system prompts in one file
│   │   ├── stages/
│   │   │   ├── __init__.py
│   │   │   ├── segmenter.py
│   │   │   ├── abstractor.py
│   │   │   ├── parameterizer.py
│   │   │   └── validator.py
│   │   └── schema.py                ← dataclasses: TraceEvent, Step, Skill
│   ├── codify/
│   │   ├── __init__.py
│   │   ├── skill_md.py              ← Skill → SKILL.md text
│   │   └── replay_script.py         ← emit scripts/replay.py from a Skill
│   ├── replay/
│   │   ├── __init__.py
│   │   ├── runner.py                ← parse SKILL.md, run scripts/replay.py
│   │   ├── ax_resolve.py            ← resolve a stored selector at runtime
│   │   ├── actions.py               ← click / type / press / wait primitives
│   │   └── vision_fallback.py       ← stub for v0; raises NotImplementedError
│   └── utils/
│       ├── __init__.py
│       ├── ax_helpers.py
│       └── logging.py
├── tests/
│   ├── conftest.py
│   ├── test_ax_snapshot.py
│   ├── test_ax_selector.py
│   ├── test_session_writer.py
│   ├── test_codify.py
│   └── test_replay_actions.py       ← skipped on CI; manual run only
├── examples/
│   ├── calculator_handwritten/      ← Phase 3 fixture
│   │   ├── SKILL.md
│   │   └── scripts/replay.py
│   └── calculator_demo/             ← Phase 6 end-to-end output
└── docs/
    └── DEMO.md                      ← Phase 7 (the tweet + GIF copy)
```

---

## 2. Dependencies (pin in pyproject.toml)

**Core runtime:**
- `pyobjc-core`
- `pyobjc-framework-Cocoa`
- `pyobjc-framework-Quartz`
- `pyobjc-framework-ApplicationServices`
- `pyobjc-framework-CoreGraphics`
- `anthropic >= 0.40`
- `typer >= 0.12`
- `rich >= 13` (for nice CLI output)
- `python-dotenv`

**Dev:**
- `pytest`
- `pytest-cov`
- `ruff`
- `mypy`

Do NOT add: `langchain`, `langgraph`, `crewai`, `autogen`, `playwright`, `selenium`. Out of scope.

---

## Phase 0 — Scaffolding and `forge doctor`

**Goal:** project set up, `forge doctor` reports environment readiness.

### Tasks

1. Initialize git repo if not already. Create `.gitignore` (include `.venv/`, `*.pyc`, `__pycache__/`, `.env`, `sessions/`, `.DS_Store`, `dist/`, `*.egg-info/`).
2. Create `pyproject.toml` with the deps above. Project name `skill-forge`, console script `forge = "skill_forge.cli:app"`.
3. `uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"`.
4. Create `LICENSE` (MIT, current year, author placeholder Rahul).
5. Create `.env.example` containing `ANTHROPIC_API_KEY=`.
6. Build the package skeleton: every dir in section 1 with empty `__init__.py`, but only stub the files needed for doctor:
   - `skill_forge/cli.py` — Typer app with sub-commands `record`, `build`, `replay`, `doctor`. Only `doctor` is implemented; the others raise `typer.Exit(1)` with "not implemented yet".
   - `skill_forge/recorder/permissions.py` — two functions: `accessibility_granted() -> bool`, `screen_recording_granted() -> bool`. Use `AXIsProcessTrusted()` for the first; for screen recording, attempt a 1×1 `CGWindowListCreateImage` on the main display and return whether the result is non-null (the OS prompts on first call).
   - `skill_forge/utils/logging.py` — `setup_logging(level=logging.INFO)`.
7. Implement `forge doctor`: prints a table (use `rich.table.Table`) of environment checks:
   - Python version ≥ 3.11
   - macOS version (read via `platform.mac_ver()`)
   - PyObjC importable
   - Accessibility permission (call `accessibility_granted()`)
   - Screen Recording permission
   - `ANTHROPIC_API_KEY` set (don't print the value, just yes/no)
   - `anthropic` SDK importable

### Done when

- `forge doctor` runs and prints a clean table.
- All checks PASS on the dev machine; permissions can be FAIL initially — the table just has to render.
- `pytest` runs with zero tests collected without errors.
- `ruff check .` passes.

### Commit
`phase 0: project scaffold and forge doctor`

---

## Phase 1 — AX snapshot + selector

**Goal:** given the focused UI element, produce a stable, portable selector string and a JSON snapshot of the surrounding subtree. Hand-test against macOS Calculator.

### Why this first

The recorder and the replayer both depend on the selector format. If we don't pin this format down before recording, we'll have to re-record everything later. Build it, test it interactively, freeze the format.

### Selector format (freeze this)

A path of segments separated by `/`, each segment of the form:

```
AXRole[attr1='value1'; attr2='value2']
```

Attributes (in this priority order, include up to 3 that are non-empty):

- `id` — `AXIdentifier` if set
- `title` — `AXTitle` if set
- `value` — `AXValue` if set and short (≤32 chars)
- `desc` — `AXDescription` if set
- `pos` — index among siblings of the same role (e.g. `pos=3`), used as a last resort

App-level segment uses bundle id: `AXApplication[bundle='com.apple.calculator']`.

Example for the Calculator "8" button:

```
AXApplication[bundle='com.apple.calculator']/AXWindow[title='Calculator']/AXGroup[pos=0]/AXButton[desc='eight']
```

### Tasks

1. `skill_forge/utils/ax_helpers.py` — small helpers: `get_attr(elem, name)` wrapping `AXUIElementCopyAttributeValue`; `get_children(elem)`; `get_role(elem)`; `get_pid(elem)`; `bundle_id_for_pid(pid)` (use `NSRunningApplication`).
2. `skill_forge/recorder/ax_selector.py`:
   - `selector_for(elem) -> str` — walk parent chain to root via `kAXParentAttribute`, build the path.
   - `find_by_selector(selector: str, root=None, timeout_s: float = 3.0) -> Optional[AXUIElementRef]` — depth-first search rooted at `AXUIElementCreateSystemWide()` (or a given app), matching segments in order. Polls every 100ms up to timeout because UI can be loading.
3. `skill_forge/recorder/ax_snapshot.py`:
   - `snapshot_focused() -> dict` — returns `{selector, role, attrs, parent_chain[3], children[10]}`. Bound depth so JSONL doesn't explode.
4. Add a hidden CLI subcommand `forge _devsnap` that prints `snapshot_focused()` as JSON. Useful for interactive testing — won't be documented.

### Acceptance test

- Open Calculator.app.
- Click the "8" button so it has focus (or just click it once).
- Run `forge _devsnap`.
- Verify the printed selector starts with `AXApplication[bundle='com.apple.calculator']` and contains `AXButton`.
- In a Python REPL: `from skill_forge.recorder.ax_selector import find_by_selector; e = find_by_selector("<that selector>"); print(get_attr(e, "AXTitle"))` — must return non-None.
- Unit test in `tests/test_ax_selector.py`: round-trip a synthetic selector string through a parser and a serializer and assert equality. (No Mac UI in unit tests.)

### Don't do

- Don't try to make selectors match across machines. They're per-user-session. Cross-machine portability is a v2 problem.
- Don't store full AX trees per event. Bound depth is the whole point.

### Commit
`phase 1: ax selectors + snapshots`

---

## Phase 2 — Recorder

**Goal:** `forge record --out sessions/demo1` runs in foreground, captures mouse, keyboard, app-switch, and AX-snapshot events plus periodic screenshots, exits cleanly on Ctrl-C, leaves behind a parseable session directory.

### Session directory layout

```
sessions/demo1/
├── meta.json            # start_ts, end_ts, macos_version, hostname
├── trace.jsonl          # one event per line
└── frames/
    ├── 0001.png
    ├── 0002.png
    └── ...
```

### Event schema (each line of trace.jsonl)

```json
{
  "ts": 1714857600.123,
  "type": "click | keydown | keyup | scroll | app_switch | frame | ax_snapshot",
  "data": { ... type-specific ... }
}
```

- `click.data`: `{x, y, button, modifiers, ax_selector_at_point}`
- `keydown.data`: `{keycode, chars, modifiers}` — coalesce typed text into `text_input` events of consecutive printable characters (don't store passwords nakedly — see "Don't do" below)
- `app_switch.data`: `{from_bundle, to_bundle, window_title}`
- `frame.data`: `{path: "frames/0001.png", reason: "interval" | "app_switch" | "click"}`
- `ax_snapshot.data`: full `snapshot_focused()` output, captured before each click and on each app_switch

### Tasks

1. `skill_forge/recorder/event_tap.py` — register a `CGEventTap` on the main `CFRunLoop`. CRITICAL: The tap callback MUST return in < 2ms or macOS will kill it. Do NOT do any AXUIElement lookups in the callback. On click, call `CGEventGetLocation`, push `(timestamp, x, y, event_type)` to a `queue.Queue`, and return the event immediately.
2. `skill_forge/recorder/screen_capture.py` — `capture_main_display(out_path)` using `CGWindowListCreateImage` + `NSBitmapImageRep` to write PNG. Provide `every_n_seconds_loop(out_dir, interval=2.0, stop_event)` running in its own thread.
3. `skill_forge/recorder/session.py` — manages the writer thread. The worker thread blocks on the queue. When it pops a click coordinate, it immediately calls `AXUIElementCopyElementAtPosition` to get the element ref, runs the depth-bounded `snapshot_focused()` traversal, and writes the final merged JSON to disk.
4. Wire `forge record --out PATH` to `RecorderSession`.

### Acceptance test

- `forge record --out sessions/calc1`.
- Open Calculator. Click `2`, `+`, `2`, `=`. Quit Calculator. Ctrl-C the recorder.
- Inspect `sessions/calc1/`:
  - `meta.json` has both `start_ts` and `end_ts`.
  - `trace.jsonl` contains at least: 1 `app_switch` (Terminal→Calculator), 4 `click` events with `ax_selector_at_point` containing `AXButton`, 1 `app_switch` to Finder/Terminal at quit.
  - `frames/` has at least 4 PNGs.
- Hand-verify: `jq -r '.type' sessions/calc1/trace.jsonl | sort | uniq -c` shows reasonable counts.

### Don't do

- Don't capture key events when an app's frontmost window is a known password field (basic mitigation: skip keydown events when the focused element's `AXSubrole` is `AXSecureTextField`). README this clearly anyway.
- Don't capture screens when the screensaver is on. (`CGSessionCopyCurrentDictionary`-based check is fine.)
- Don't coalesce mouse moves at this stage. If you need movement later, add a separate `mousemove` type. v0 only cares about clicks.

### Commit
`phase 2: recorder`

---

## Phase 3 — Codify (the SKILL.md emitter), with a hand-written fixture skill

**Goal:** before introducing any LLM, prove the SKILL.md format and the replayer end-to-end on a hand-written skill. This phase produces a known-good fixture.

### Tasks

1. `skill_forge/pipeline/schema.py` — dataclasses:

```python
@dataclass
class Step:
    name: str               # human-readable, e.g. "Click eight"
    action: str             # "click" | "type" | "press_key" | "wait" | "app_launch"
    selector: str | None    # AX selector for the target
    args: dict              # action-specific: {text: "..."} for type, etc.
    assertions: list[str]   # post-conditions, free-form English

@dataclass
class Parameter:
    name: str
    type: str               # "string" | "number" | "file" | "date"
    description: str
    default: str | None

@dataclass
class Skill:
    name: str
    description: str
    parameters: list[Parameter]
    steps: list[Step]
```

2. `skill_forge/codify/skill_md.py` — `skill_to_md(skill: Skill) -> str` produces this format:

```markdown
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
2. Click digits for `${a}`
3. Click `+`
4. Click digits for `${b}`
5. Click `=`
6. Read the result label and print it
```

3. `skill_forge/codify/replay_script.py` — `skill_to_replay_py(skill: Skill) -> str` produces a self-contained `scripts/replay.py` that imports `skill_forge.replay.actions` and `skill_forge.replay.ax_resolve` and runs the steps. Parameters arrive via `--params` JSON.
4. Hand-write `examples/calculator_handwritten/SKILL.md` and `examples/calculator_handwritten/scripts/replay.py` matching the schema you just designed. This is the truth-test for Phase 4.
5. Unit test `tests/test_codify.py`: build a `Skill` programmatically, render it through both emitters, snapshot-test the output.

### Done when

- The hand-written calculator skill exists and is valid.
- `python -c "from skill_forge.codify.skill_md import skill_to_md; ..."` round-trips.
- Snapshot tests pass.

### Commit
`phase 3: skill schema, codifier, hand-written calculator fixture`

---

## Phase 4 — Replayer

**Goal:** `forge replay examples/calculator_handwritten --params '{"a": 7, "b": 5}'` actually drives Calculator and prints `12`.

### Tasks

1. `skill_forge/replay/actions.py`:
   - `click(selector_or_point, button="left")` — if string, resolve via `ax_resolve.find()`; if tuple, do a coordinate click via `CGEventCreateMouseEvent`. Prefer `AXUIElementPerformAction(elem, kAXPressAction)` when the element supports it (faster, no cursor jumping); fall back to coordinate click otherwise.
   - `type_text(text)` — `CGEventKeyboardSetUnicodeString` for arbitrary unicode; one event per character with a tiny inter-key sleep (10ms).
   - `press_key(keycode, modifiers=())` — `CGEventCreateKeyboardEvent`.
   - `app_launch(bundle_id)` — `NSWorkspace.sharedWorkspace().launchAppWithBundleIdentifier_options_additionalEventParamDescriptor_launchIdentifier_(...)`.
   - `wait(seconds)` and `wait_for(selector, timeout)`.
2. `skill_forge/replay/ax_resolve.py`:
   - `find(selector: str, timeout_s=3.0) -> AXUIElementRef` — wraps Phase-1 `find_by_selector` with retry + better errors.
   - On miss, raise `SelectorNotFound(selector, last_seen_app, suggested=...)` where `suggested` contains the closest selector by Levenshtein on attrs (best-effort hint).
3. `skill_forge/replay/runner.py`:
   - `run_skill(skill_dir: Path, params: dict, dry_run=False)` — parses SKILL.md frontmatter, validates required params, then `python scripts/replay.py --params <json>` as a subprocess. Streams stdout/stderr to the user.
4. Wire `forge replay PATH --params JSON` to the runner.
5. `skill_forge/replay/vision_fallback.py` — leave as stub: `def fallback(*args, **kwargs): raise NotImplementedError("vision fallback ships in v0.2")`. Don't try to build vision in the weekend.

### Acceptance test

- Quit any open Calculator.app.
- `forge replay examples/calculator_handwritten --params '{"a": 7, "b": 5}'`.
- Calculator launches, you see digits being clicked, and the program's stdout is `12`.
- Repeat with `'{"a": 12, "b": 30}'` and confirm `42`.
- Repeat once more with the previous two cases as a regression check.

### Don't do

- Don't make replay async. Synchronous, blocking, easy to debug. Speed is fine for v0.
- Don't add retry-on-LLM-replan. The deterministic replay is the contract.

### Commit
`phase 4: replayer + calculator end-to-end`

---

## Phase 5 — The 4-stage Claude pipeline

**Goal:** `forge build sessions/calc1` produces a `Skill` object equivalent to (or better than) the hand-written calculator fixture.

### Architecture decision: use the `anthropic` SDK directly

For this weekend, do NOT use the Claude Agent SDK to orchestrate the pipeline. Each stage is a single Claude call with a structured prompt and JSON output. The "multi-agent" character lives in the separation of concerns, not in concurrent execution. This is faster, cheaper, easier to debug, and easier to mock in tests.

Each stage:
- gets a system prompt from `prompts.py`
- gets the user message = previous stage's output (+ raw trace for stage 1)
- responds with JSON only (use `messages.create` with `system=...` and instruct strict JSON, no markdown fences)
- the orchestrator parses, validates against `schema.py`, and passes forward.

### Tasks

1. `skill_forge/pipeline/claude_client.py` — thin wrapper:

```python
def call_json(system: str, user: str, model: str = "claude-sonnet-4-6", max_tokens: int = 4096) -> dict
```

Strips ```json fences if present, parses, raises `BadJSONFromModel` with the raw response on failure.

2. `skill_forge/pipeline/prompts.py` — four constants. Sketches:

**SEGMENTER_SYSTEM**
```
You are the SEGMENTER stage of a pipeline that converts a recorded macOS user
demonstration into a reusable skill.

Input: a JSONL trace of {ts, type, data}. Some events are noise: idle frames,
focus blips, mouse-up after a click, repeated screenshots while nothing
happens. Some events together form one logical step (e.g. a sequence of
keydowns spelling "hello world" is ONE step).

Output a JSON array of segments. Each segment is:
  {start_idx, end_idx, summary}
where indices are 0-based into the input trace and summary is a 5-10 word
description of what the user is doing.

Output ONLY valid JSON, no prose.
```

**ABSTRACTOR_SYSTEM**
```
You are the ABSTRACTOR stage. Input: the original trace plus a list of
segments from the segmenter. Output: a JSON array of structured Steps.

Each step:
  {name, action, selector, args, raw_event_indices}
where:
  action ∈ {"click", "type", "press_key", "wait", "app_launch"}
  selector is the AX selector for the target (use the ax_snapshot data nearest
    to the relevant event)
  args is action-specific (e.g. {"text": "..."} for type)

Steps must be in chronological order. Output ONLY valid JSON.
```

**PARAMETERIZER_SYSTEM**
```
You are the PARAMETERIZER stage. Input: a list of structured Steps.

Identify which step args contain values that the USER would change between
runs vs values that are part of the workflow itself.

Examples that should usually be parameters:
  - file paths the user typed/pasted
  - search queries
  - dates, dollar amounts
  - email recipients

Examples that usually should NOT be parameters:
  - app launches (the bundle id is the workflow)
  - menu navigation clicks
  - the "submit" button

Output JSON:
{
  "parameters": [{name, type, description, default?}],
  "steps": [...steps with args using ${param_name} placeholders...]
}

Choose a short, descriptive name and a short description for each parameter.
Output ONLY valid JSON.
```

**VALIDATOR_SYSTEM**
```
You are the VALIDATOR stage. Input: the parameterized Steps.

For each step, write 0-3 assertions about the world AFTER the step succeeds.
Assertions are short English sentences a human can read; they will not be
machine-evaluated in v0 — they ride along as documentation that future
versions will check.

Examples:
  - "Calculator app is frontmost"
  - "The digit '7' has appeared in the result label"
  - "A new untitled note has opened"

Also propose a final SKILL name (kebab-case, ≤30 chars) and a 1-sentence
description.

Output JSON:
{
  "skill_name": "...",
  "skill_description": "...",
  "steps": [...steps with assertions field added...]
}

Output ONLY valid JSON.
```

3. `skill_forge/pipeline/stages/*.py` — one tiny module per stage; each has `run(input) -> output_dict` calling `call_json`.
4. `skill_forge/pipeline/orchestrator.py` — `build_skill(session_dir: Path) -> Skill`. Loads the trace, runs the four stages in order, assembles a `Skill` dataclass, returns it.
5. Wire `forge build PATH --out OUTPUT_DIR` to: `build_skill` → `skill_to_md` + `skill_to_replay_py` → write to `OUTPUT_DIR/SKILL.md` and `OUTPUT_DIR/scripts/replay.py`.
6. Add a `--mock` flag that bypasses all four LLM calls and returns a fixed `Skill` (used in tests).
7. Tests in `tests/test_pipeline.py` should monkey-patch `claude_client.call_json` to return canned responses for each stage; assert the orchestrator assembles a valid Skill.

### Acceptance test (the real one)

- Use `sessions/calc1` from Phase 2.
- `forge build sessions/calc1 --out examples/calculator_demo`.
- Diff the generated SKILL.md against the hand-written one. Names will differ; the shape (parameters, steps, selectors) should be near-equivalent.
- `forge replay examples/calculator_demo --params '{"a": 7, "b": 5}'` prints `12`.

### Don't do

- Don't share a single mega-prompt across stages. The separation is the whole point — each stage gets only what it needs.
- Don't pass the screen frames into the prompts in v0. Text-only is enough for Calculator and most form-style workflows. Frames are a v0.2 lever for vision fallback.
- Don't retry on JSON parse failure more than 2 times. Surface the raw response and let the user fix the trace.

### Commit
`phase 5: claude pipeline (segmenter → abstractor → parameterizer → validator)`

---

## Phase 6 — End-to-end demo + a real workflow

**Goal:** record-build-replay a workflow that's not Calculator. Pick a tweetable one.

### Recommended demo workflows (rank order)

1. **Notes daily-journal:** open Notes → create new note → type today's date as title → type a bulleted template → cmd+s. Parameters: date, mood, top-3-tasks. Demos `type_text` heavily; visually clean.
2. **Spotlight launch + search:** cmd+space → type query → enter. Tiny but instantly readable. Good as a unit test for the pipeline.
3. **Reminders entry:** open Reminders → click new reminder → type text + date. Parameter extraction is non-trivial here (the date should become a parameter; the list shouldn't).

Skip Concur/Costco for v0 — those need authenticated browsers, which is a Phase 8 problem.

### Tasks

1. Pick one of the above. Record it (`forge record`).
2. Build it (`forge build`).
3. Replay with two distinct parameter sets.
4. Capture a 60-second screen recording showing record → build (terminal output of stages) → replay → replay-with-different-params.
5. If anything is off (selector miss, wrong parameterization), patch prompts, not code. Re-run `forge build`. If you find a code bug, file an issue in the repo and keep going — don't yak-shave on the demo path.

### Done when

- The recorded video exists at `docs/demo.mp4` (don't commit binaries to the repo; commit a script that builds the GIF from the mp4 with ffmpeg).
- Both replay invocations succeed clean on a fresh launch.

### Commit
`phase 6: end-to-end demo (<workflow name>)`

---

## Phase 7 — README, ship, post

**Goal:** the repo, when stumbled across cold, makes the value obvious in 10 seconds.

### Tasks

1. `README.md`:
   - First paragraph is the punchline ("teach your Mac once, forever after any Claude agent can replay it").
   - Embedded GIF immediately after.
   - Three-command quickstart: install · doctor · record · build · replay.
   - Architecture diagram (the one in this file's Phase 5 acceptance section).
   - "How it works" — 4 stages, one line each.
   - Limitations: macOS only, AX-only (no vision fallback yet), single-window workflows work best.
   - Privacy: everything is local, only `trace.jsonl` summaries (NOT screen frames) are sent to Claude during `forge build`. Make this prominent.
   - Roadmap section for v0.2: vision fallback, cross-machine selector portability, multi-window workflows.
2. `docs/DEMO.md` — the tweet copy and a 4-frame storyboard. Pre-write the post so when it's time to ship you don't get cute on Twitter.
3. Submit a PR to a couple of awesome-claude-* lists once the repo is public.

### Done when

- A non-technical friend can read the README and explain back what Skill Forge does in one sentence.

### Commit
`phase 7: readme + demo docs + ship`

---

## Acceptance for the whole project

The project is "shipped" when, on a clean checkout on a fresh-permissions Mac, the following one-liner works:

```bash
git clone <url> && cd skill-forge && uv venv && source .venv/bin/activate && \
  uv pip install -e . && export ANTHROPIC_API_KEY=... && \
  forge doctor && \
  forge replay examples/calculator_handwritten --params '{"a":7,"b":5}'
```

…and the user, after granting permissions, can run `forge record`, `forge build`, `forge replay` on their own workflow.

---

## Things Claude Code is likely to get wrong — pre-empt these

1. **PyObjC import paths.** It will try `from Quartz import CGEventTapCreate` and fail because some symbols live in `Quartz.CoreGraphics`. When in doubt, do `import Quartz; print(dir(Quartz))` once and pin the actual paths.
2. **CGEventTap callback signature.** It's `(proxy, type_, event, refcon) -> event` and it MUST return the event (or `None` to drop). Forgetting the return turns the Mac into molasses.
3. **CFRunLoop ownership.** The event tap needs `CFRunLoopAddSource` on the main run loop. Run capture loop on the main thread; do file writes on a worker thread fed by a queue.
4. **Accessibility permissions.** First run will appear to hang because macOS pops a permission dialog. The CLI should detect "tap creation returned NULL" and print a clear message: "grant Accessibility in System Settings → Privacy & Security → Accessibility, then re-run."
5. **The `claude-sonnet-4-6` constant.** Hardcode it in exactly one place (`pipeline/orchestrator.py`). Don't sprinkle model strings around.
6. **JSON-only model output.** The model occasionally fences output in ```json. Strip both the opening and closing fence, then `json.loads`. If that fails, dump the raw to a `last_failed_response.json` file in the working dir and raise.
7. **Don't pass the entire trace to every stage.** The segmenter sees the full trace. The abstractor sees segments + the trace slices each segment indexes into. The parameterizer sees only abstracted steps. The validator sees only parameterized steps. This keeps token usage bounded.
8. **Selector resolution is racy with app launches.** `wait_for(selector, timeout=5)` polling at 100ms is the right default. Use it after every `app_launch`.

---

## Stretch (only if Sunday afternoon arrives early)

- `forge studio` — a tiny Tk/Textual TUI that visualizes a session: timeline of events, selected event's frame on one side, AX snapshot tree on the other. Great for the README screenshot.
- "Re-record this step" — interactive editing mode that re-records a single step and patches it into an existing skill.
- A small `forge eval` command that replays a skill 10 times and reports success/fail rate. Cheap insurance against drift.

Skip these if the demo isn't yet posted. Post first.
