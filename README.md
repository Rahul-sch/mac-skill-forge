# Skill Forge

[![ci](https://github.com/Rahul-sch/mac-skill-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/Rahul-sch/mac-skill-forge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![macOS 14+](https://img.shields.io/badge/macOS-14%2B-blue.svg)](https://www.apple.com/macos/)

**Teach your Mac once, then replay the workflow safely from Codex, Claude, or the CLI.**

Record yourself doing something on macOS—composing the morning status email, filling out a daily journal, or another repetitive sequence of clicks and typing. Skill Forge asks an LLM to extract the reusable structure and parameters, validates the result, and emits a data-only `skill.json`, agent-readable `SKILL.md`, and a safe compatibility wrapper.

> **v0.2:** macOS 14+ only. Tested on Apple Silicon. AX-friendly apps work best; apps that hide their controls from Accessibility remain out of scope.

## Quickstart

The fast path (no clone needed; just gets you the `forge` CLI):

```bash
brew install pipx && pipx ensurepath
pipx install git+https://github.com/Rahul-sch/mac-skill-forge.git
export GROQ_API_KEY=gsk_...    # get one free at https://console.groq.com
forge doctor                   # verify environment + permissions
```

Or, for hacking on it:

```bash
git clone https://github.com/Rahul-sch/mac-skill-forge.git
cd mac-skill-forge
brew install uv                # if you don't already have it
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
export GROQ_API_KEY=gsk_...
forge doctor
```

`forge doctor` checks Python, macOS, PyObjC, Accessibility, Input Monitoring, and the build API key. Grant Accessibility and Input Monitoring to the terminal app that launched `forge`, then fully quit and relaunch that terminal. Screen Recording is optional and is only needed when recording with `--capture-frames`.

Then the loop:

```bash
forge record --out sessions/my_workflow      # do the thing once, Ctrl-C
forge build sessions/my_workflow --out skills/my_workflow  # confirms before upload
forge replay skills/my_workflow --params '{"recipient":"boss@x.com","subject":"hi","body":"..."}' --dry-run
forge replay skills/my_workflow --params '{"recipient":"boss@x.com","subject":"hi","body":"..."}'
forge install skills/my_workflow --agent codex             # or: --agent claude
```

## How it works

Four stages, one LLM call each:

1. **Segmenter** — collapses the raw event trace (clicks, keypresses, app switches) into a small list of logical segments with summaries.
2. **Abstractor** — turns segments into structured steps (`click`, `type`, `press_key`, `scroll`, `wait`, `app_launch`) with AX selectors.
3. **Parameterizer** — identifies which step args are user-variable inputs (recipients, subjects, dates) vs workflow constants (the `Send` button), substitutes `${name}` placeholders.
4. **Validator** — names and describes the skill; a deterministic local validator then rejects malformed actions, selectors, parameters, and placeholders.

Output: `skill.json` is the validated source of truth, `SKILL.md` explains the skill to an agent, and `scripts/replay.py` is a thin wrapper around the trusted manifest runner. Skills without a manifest never execute unless the user explicitly passes `--allow-script`.

```
record (CGEventTap)        build (4 LLM calls)         replay (deterministic)
─────────────────          ─────────────────────       ──────────────────────
clicks                     1. SEGMENTER                schema validation
keypresses    →  trace → { 2. ABSTRACTOR  } → skill → { + AX resolution/focus }
app_switches               3. PARAMETERIZER            + trusted actions only
ax_snapshots               4. VALIDATOR                + explicit dry-run
```

## Privacy

Everything is local except `forge build`. Build sends the recorded typed text, click/keyboard events, AX selectors, and AX snapshot values to the configured LLM endpoint after showing a confirmation. **Screen frames are never uploaded.** Frames are off by default; `forge record --capture-frames` stores them locally for review. Intermediate model responses are also off by default and can be retained with `--keep-debug`.

Secure-field keystrokes are never recorded. A redacted marker is written instead, and build stops rather than creating an incomplete automation. Use `forge build --mock` to test the local pipeline without making LLM calls.

## LLM provider

The default is Groq's OpenAI-compatible chat-completions endpoint and `llama-3.3-70b-versatile`. Configure another OpenAI-compatible provider without editing code:

```bash
export FORGE_API_KEY=...
export FORGE_LLM_URL=https://provider.example/v1/chat/completions
export FORGE_MODEL=provider-model-id
```

A typical build makes four model calls. Pricing and availability depend on the selected provider.

## Limitations (v0)

- **macOS only.** Apple Silicon, macOS 14+. PyObjC + Accessibility API are the bedrock; no plan for Linux/Windows.
- **AX-only.** If an app doesn't expose its UI through Accessibility, Skill Forge can't see it. Web apps inside Safari are partially exposed; Electron apps vary widely. There's a `vision_fallback.py` stub for v0.2.
- **Single-window workflows.** Multiple matching windows can still be ambiguous. Close duplicate drafts/windows before replaying a sensitive workflow.
- **App-specific autocomplete is non-deterministic.** Mail's recipient autocomplete sometimes resolves a typed email to the user's own contact, sometimes to whatever Mail picks first. Subject and body fields are unaffected.
- **Single-demonstration parameterization is hard.** From one recording of `2 + 2`, the parameterizer has to infer that the digits are the parameters. Sometimes it gets it right, sometimes it bakes in `2` as a constant. Multi-demonstration input (record `2+2` and `7+5`, diff them) is a v0.2 lever that would make this trivial.
- **Review before replay.** `forge replay ... --dry-run` displays the resolved defaults and complete action plan. English assertions in `SKILL.md` are explanatory; only action-level failures and explicit `read` steps are machine checked today.

## Roadmap (v0.3)

- **Vision fallback** — when AX selector resolution fails, fall back to OpenCV pixel matching against the captured frames. Closes the "no AX coverage" gap for Electron apps and the like.
- **Multi-demonstration parameterization** — record the same workflow with two different parameter sets, diff them at the abstract-step level. The varying args are the parameters.
- **Cross-machine selector evaluation** — selectors now prefer stable IDs and tolerate anonymous hierarchy changes; a broader app/version test corpus is still needed.
- **Multi-window disambiguation** — when several windows of the same app match a selector's leaf, prefer the most-recently-frontmost one.
- **`forge studio`** — a TUI that visualizes a session: timeline of events on one side, AX snapshot tree on the other. Great for debugging selector misses.
- **Richer postconditions** — generate structured, app-specific checks rather than explanatory assertions alone.

## Project layout

```
skill_forge/
├── recorder/      # CGEventTap + AX snapshots + screen capture
├── pipeline/      # 4 stages + claude_client + prompts + orchestrator
├── codify/        # Skill -> validated skill.json, SKILL.md, safe wrapper
├── replay/        # actions (click/type/...), ax_resolve, runner
└── utils/         # AX helpers, logging
```

See [`PLAN.md`](PLAN.md) for the phase-by-phase build journal — the constraints, what got cut, and the architecture decisions that load-bear the rest of the system.

## Reliability checks

```bash
forge replay skills/my_workflow --params '{...}' --dry-run
forge eval skills/my_workflow --params '{...}' --runs 10
```

`eval` reports the observed process-level success rate. For workflows with meaningful side effects, use safe test data and add an explicit `read` step or manual outcome check.

## License

MIT — see [LICENSE](LICENSE).
