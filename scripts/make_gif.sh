#!/usr/bin/env bash
# Convert an mp4 screen recording into a small, embed-ready GIF.
# Two-pass with a palette for decent color and reasonable file size.
#
#   scripts/make_gif.sh docs/demo.mp4 docs/demo.gif
#
# Override fps / width with env vars: FPS=15 W=900 scripts/make_gif.sh ...

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <input.mp4> <output.gif>" >&2
    exit 64
fi

IN="$1"
OUT="$2"
FPS="${FPS:-12}"
W="${W:-960}"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ffmpeg not installed. Run: brew install ffmpeg" >&2
    exit 1
fi
if [ ! -f "$IN" ]; then
    echo "input file not found: $IN" >&2
    exit 1
fi

PALETTE="$(mktemp -t skill-forge-palette.XXXXXX).png"
trap 'rm -f "$PALETTE"' EXIT

ffmpeg -y -i "$IN" -vf "fps=${FPS},scale=${W}:-1:flags=lanczos,palettegen=stats_mode=diff" "$PALETTE"
ffmpeg -y -i "$IN" -i "$PALETTE" -lavfi "fps=${FPS},scale=${W}:-1:flags=lanczos[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle" "$OUT"

ls -lh "$OUT"
