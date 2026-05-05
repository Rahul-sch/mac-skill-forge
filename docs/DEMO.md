# Demo doc — tweet copy + storyboard

Pre-write the post so when it's time to ship you don't get cute on Twitter.

## The pitch

> Recorded myself sending one Monday status email.
>
> Now any Claude agent can draft it in 3 seconds. I review and hit send.
>
> https://github.com/Rahul-sch/mac-skill-forge

Alternative copy if you want the punchier version:

> Hate writing the same email every Monday?
>
> Skill Forge watches you do it once, then any Claude agent can replay it with new content. Mac-only. Open source.
>
> https://github.com/Rahul-sch/mac-skill-forge

## 4-frame storyboard

The video is ~60 seconds. Each frame ~15s.

1. **`forge record --out sessions/status_email`** (the demonstration)
   - Mail.app opens
   - User clicks `cmd+N` for a new compose
   - User types: `boss@x.com`, then Tab, then `Monday status — 5/5`, then Tab, then a 3-line body
   - User hits Ctrl-C in terminal
   - Show terminal: "Session complete: sessions/status_email"

2. **`forge build sessions/status_email --out skills/status_email`** (the magic)
   - Show terminal logs streaming:
     ```
     [1/4] segmenter -> 5 segments
     [2/4] abstractor -> 8 steps
     [3/4] parameterizer -> 3 parameters
     [4/4] validator -> skill_name=send-email
     wrote skills/status_email/SKILL.md and scripts/replay.py
     ```
   - Cut to `cat skills/status_email/SKILL.md` showing the 3 parameters and 8 steps

3. **`forge replay skills/status_email --params '...'`** (different content)
   - Same Mail compose window pops open
   - Recipient: `someone-else@x.com`
   - Subject: `Quick update on the migration`
   - Body: a 3-liner with different content
   - All filled in automatically over ~3 seconds

4. **The kicker** — show that the SKILL.md is just a markdown file
   - `cat skills/status_email/SKILL.md` again
   - "any Claude agent can read this file and call replay.py with whatever inputs it wants"

## Recording the actual video

Use macOS's built-in screen recorder (cmd+shift+5) or `screen-recorder-cli`. Aim for:
- 1280×720 minimum
- 30fps
- ~60 seconds total
- No system audio (or mute notifications first)

Trim the obvious dead space (waiting for Mail to launch, waiting on LLM calls). Keep the latency for the LLM calls visible — it's part of the honesty.

Save the .mp4 at `docs/demo.mp4` (gitignored — too big for the repo). Then convert to GIF with `scripts/make_gif.sh docs/demo.mp4 docs/demo.gif`. Commit only the GIF (or a smaller mp4 if the GIF is huge).

## Where to post

- Twitter / X with the pitch above and the GIF embedded
- HN as a Show HN — be ready for "why not Selenium / Playwright / AppleScript" questions; the answer is "those need authoring, this learns from one demonstration"
- r/MacOSAutomation, r/LocalLLaMA (it runs on Groq's free tier)
- A few "awesome-claude" lists once they index it
