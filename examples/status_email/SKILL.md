---
name: send-email
description: Sends a new email with specified recipient, subject, and body using the Mail app
---

# send-email

Sends a new email with specified recipient, subject, and body using the Mail app

## Parameters
- `recipient` (string, default=rahul.bainsla2005@gmail.com): Recipient email
- `subject` (string, default=Morning status — 2026-05-04): Email subject
- `body` (string, default=Yesterday: shipped phase 5 of skill-forge. Today: phase 6 demo recording. Blockers: none.): Email body

## How to invoke
Run: `python scripts/replay.py --params '{"recipient": "rahul.bainsla2005@gmail.com", "subject": "Morning status \u2014 2026-05-04", "body": "Yesterday: shipped phase 5 of skill-forge. Today: phase 6 demo recording. Blockers: none."}'`

## Steps (for reference; replay.py is the source of truth)
1. Launch Mail app
2. Wait for window to appear
3. Open new message
4. Type recipient email
5. Click on subject field
6. Type email subject
7. Move to email body field
8. Type email body
