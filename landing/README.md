# landing/

Static one-page launch site for Skill Forge.

## Preview locally

```bash
python3 landing/server.py
# open http://localhost:8000
```

The loopback-only server serves the page and exposes a token-protected local demo
endpoint. Clicking **Run Mail draft demo** requires confirmation, then launches
the validated `examples/status_email` manifest. It composes but never sends.

## Add the optional background GIF

Drop an animated GIF at `landing/bg.gif`. Without it, the page uses its built-in
gradient background. Background media is intentionally gitignored.

Recommended source: a slow ambient loop (think product photography b-roll, abstract gradient, or — fitting for Skill Forge — a screen recording of `forge replay` driving Mail or Calculator at half speed).

Convert a short video to a compact GIF if needed:

```bash
ffmpeg -i input.mov -vf "fps=15,scale=1280:-1:flags=lanczos" -t 8 landing/bg.gif
```

## Customizing

Single file: `index.html` has Tailwind via CDN, fonts from Google, and embedded CSS for the liquid-glass effect and entrance animations. No build step.

The visual spec — Instrument Serif headlines, Inter body, liquid-glass CTAs, fade-rise entrance — was given verbatim. Copy was adapted to pitch Skill Forge.
