# Skill Forge

[![ci](https://github.com/Rahul-sch/mac-skill-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/Rahul-sch/mac-skill-forge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![macOS 14+](https://img.shields.io/badge/macOS-14%2B-blue.svg)](https://www.apple.com/macos/)

**Teach your Mac once, forever after any Claude agent can replay it.**

Record yourself doing something on macOS — sending the morning status email, filling out a daily journal, anything that's a slog of clicks and typing. Skill Forge watches the demonstration, asks an LLM to figure out the structure and which inputs are parameters, and emits a `SKILL.md` plus a generated Python script you can run with different parameters next time. Your future self stops doing the chore.

> ⚠️ **v0**: macOS 14+ only. Tested on Apple Silicon. The 8-step status-email demo built and replayed end-to-end. Selectors are AX-tree only — if an app doesn't expose Accessibility, this won't work yet.

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

`forge doctor` checks Python, macOS, PyObjC, Accessibility/Screen Recording grants, and your API key. **Grant Accessibility and Screen Recording to the terminal app you launched `forge` from** (System Settings → Privacy & Security → Accessibility / Screen Recording → toggle on), then **fully quit and relaunch the terminal** before re-running. macOS only re-reads the grants on a clean launch.

Then the loop:

```bash
forge record --out sessions/my_workflow      # do the thing once, Ctrl-C
forge build sessions/my_workflow --out skills/my_workflow
forge replay skills/my_workflow --params '{"recipient":"boss@x.com","subject":"hi","body":"..."}'
```

## How it works

Four stages, one LLM call each:

1. **Segmenter** — collapses the raw event trace (clicks, keypresses, app switches) into a small list of logical segments with summaries.
2. **Abstractor** — turns segments into structured steps (`click`, `type`, `press_key`, `wait`, `app_launch`) with AX selectors.
3. **Parameterizer** — identifies which step args are user-variable inputs (recipients, subjects, dates) vs workflow constants (the `Send` button), substitutes `${name}` placeholders.
4. **Validator** — names the skill, writes a one-sentence description, and adds human-readable assertions.

Output: a self-contained `SKILL.md` (frontmatter + parameters + step list) plus a generated `scripts/replay.py` that the runner invokes via `sys.executable` so it inherits the same venv.

```
record (CGEventTap)        build (4 LLM calls)         replay (deterministic)
─────────────────          ─────────────────────       ──────────────────────
clicks                     1. SEGMENTER                AX selector resolution
keypresses    →  trace → { 2. ABSTRACTOR  } → SKILL → { + AXPress (preferred) }
app_switches               3. PARAMETERIZER            + CGEvent fallback
ax_snapshots               4. VALIDATOR                + sys.executable
```

## Privacy

Everything is local except for one outbound call type: during `forge build`, the recorded `trace.jsonl` (events + AX selector strings) is sent to the LLM provider you configured (Groq or Anthropic). **Screen frames are NEVER sent.** The `frames/*.png` files exist for human review only and are dropped from the trace before any prompt is built. Your API keys live in env vars; nothing is written to disk by Skill Forge.

If you'd rather not send selector strings either, use `forge build --mock` to bypass all LLM calls (returns a fixed dummy skill — useful for testing the rest of the pipeline).

## LLM provider

The 4-stage pipeline is provider-agnostic. By default Skill Forge talks to **Groq's `llama-3.3-70b-versatile`** because Groq has a generous free tier — change [`MODEL`](skill_forge/pipeline/orchestrator.py) and the endpoint in [`claude_client.py`](skill_forge/pipeline/claude_client.py) to use Anthropic's Claude or any other OpenAI-compatible endpoint. The model identifier is hardcoded in exactly one place by design.

Cost: a typical build is 4 calls, ~5K tokens total — fractions of a cent on Anthropic Sonnet, free on Groq's tier.

## Limitations (v0)

- **macOS only.** Apple Silicon, macOS 14+. PyObjC + Accessibility API are the bedrock; no plan for Linux/Windows.
- **AX-only.** If an app doesn't expose its UI through Accessibility, Skill Forge can't see it. Web apps inside Safari are partially exposed; Electron apps vary widely. There's a `vision_fallback.py` stub for v0.2.
- **Single-window workflows.** Mail's `_NS:41` compose-window AXIdentifier is the same for every draft window, so when multiple drafts are open, replay can race with focus transfer. Workaround for now: `killall <App>` before replay.
- **App-specific autocomplete is non-deterministic.** Mail's recipient autocomplete sometimes resolves a typed email to the user's own contact, sometimes to whatever Mail picks first. Subject and body fields are unaffected.
- **Single-demonstration parameterization is hard.** From one recording of `2 + 2`, the parameterizer has to infer that the digits are the parameters. Sometimes it gets it right, sometimes it bakes in `2` as a constant. Multi-demonstration input (record `2+2` and `7+5`, diff them) is a v0.2 lever that would make this trivial.
- **Secure text fields are skipped.** When the focused element's `AXSubrole == AXSecureTextField`, the recorder drops keystrokes silently — passwords aren't captured. Buffered non-secure text is flushed first.

## Roadmap (v0.2)

- **Vision fallback** — when AX selector resolution fails, fall back to OpenCV pixel matching against the captured frames. Closes the "no AX coverage" gap for Electron apps and the like.
- **Multi-demonstration parameterization** — record the same workflow with two different parameter sets, diff them at the abstract-step level. The varying args are the parameters.
- **Cross-machine selector portability** — current selectors include user-specific window IDs. v0.2 should normalize against bundle id + role hierarchy + stable AXIdentifiers only.
- **Multi-window disambiguation** — when several windows of the same app match a selector's leaf, prefer the most-recently-frontmost one.
- **`forge studio`** — a TUI that visualizes a session: timeline of events on one side, AX snapshot tree on the other. Great for debugging selector misses.
- **`forge eval`** — replay a skill N times and report success/fail rate. Cheap regression insurance.

## Project layout

```
skill_forge/
├── recorder/      # CGEventTap + AX snapshots + screen capture
├── pipeline/      # 4 stages + claude_client + prompts + orchestrator
├── codify/        # Skill -> SKILL.md and scripts/replay.py emitters
├── replay/        # actions (click/type/...), ax_resolve, runner
└── utils/         # AX helpers, logging
```

See [`PLAN.md`](PLAN.md) for the phase-by-phase build journal — the constraints, what got cut, and the architecture decisions that load-bear the rest of the system.

## License

MIT — see [LICENSE](LICENSE).
