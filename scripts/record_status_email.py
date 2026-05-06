"""Record the morning-status-email demo by synthesizing CGEvents.

The recorder captures synthesized events the same as physical ones (Phase 2
verified this against Calculator). After this script finishes, a fresh
session lives at sessions/status_email/ ready to be fed to `forge build`.

Demo workflow recorded:
  1. Launch Mail
  2. cmd+N (new compose window)
  3. Click the To field, type recipient
  4. Click the Subject field, type subject
  5. Click the body, type body
  6. STOP — leaves a draft in Mail's Drafts folder. Does NOT send.
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import time
from pathlib import Path

from skill_forge.replay.actions import app_launch, click, press_key, type_text, wait

OUT_DIR = Path("sessions/status_email")
FORGE = Path(".venv/bin/forge").resolve()

WIN = "AXApplication[bundle='com.apple.mail']/AXWindow[title='New Message']"
TO_FIELD = f"{WIN}/AXTextField[id='Mail.toField']"
SUBJECT_FIELD = f"{WIN}/AXTextField[id='Mail.subjectField']"

KEYCODE_N = 45
KEYCODE_TAB = 48

RECIPIENT = "you@example.com"
SUBJECT = "Morning status — 2026-05-04"
BODY = (
    "Yesterday: shipped phase 5 of skill-forge. "
    "Today: phase 6 demo recording. "
    "Blockers: none."
)


def main() -> None:
    print("[1/8] killing any existing Mail process for clean state")
    subprocess.run(["killall", "Mail"], check=False, capture_output=True)
    time.sleep(2.0)

    print("[2/8] starting forge record in background")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    proc = subprocess.Popen(
        [str(FORGE), "record", "--out", str(OUT_DIR), "--frame-interval", "1.5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2.0)
    print(f"  recorder pid={proc.pid}")

    print("[3/8] launching Mail")
    app_launch("com.apple.mail")
    wait(3.0)

    print("[4/8] cmd+N to open a new compose window")
    press_key(KEYCODE_N, modifiers=["cmd"])
    wait(1.8)

    print("[5/8] click To field, type recipient")
    click(TO_FIELD)
    wait(0.4)
    type_text(RECIPIENT)
    wait(0.6)

    print("[6/8] click Subject field, type subject")
    click(SUBJECT_FIELD)
    wait(0.4)
    type_text(SUBJECT)
    wait(0.6)

    print("[7/8] tab to body, type body")
    # The compose body is an AXWebArea — clicking it via coords is fragile.
    # Tab from Subject lands focus in the body. Cleaner.
    press_key(KEYCODE_TAB)
    wait(0.4)
    type_text(BODY)
    wait(2.0)  # let text_input idle-flush

    print("[8/8] stopping recorder (SIGINT)")
    proc.send_signal(signal.SIGINT)
    try:
        out, err = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    print(f"  recorder exit={proc.returncode}")
    if err:
        tail = err.decode(errors="replace").strip().splitlines()[-3:]
        print("  recorder stderr (tail):", "\n    ".join(tail))

    print(f"\nrecording at {OUT_DIR}")


if __name__ == "__main__":
    main()
