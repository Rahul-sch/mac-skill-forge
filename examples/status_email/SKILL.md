---
name: send-email
description: Composes a Mail draft with a specified recipient, subject, and body for review
---

# send-email

Composes a Mail draft with specified content. It does not send the message.

## Parameters
- `recipient` (string, default=you@example.com): Recipient email
- `subject` (string, default=Morning status): Email subject
- `body` (string, default=Yesterday: finished planned work. Today: continuing. Blockers: none.): Email body

## How to invoke
Run with defaults: `forge replay <this-dir>` or override values with `--params '{"recipient":"team@example.com"}'`.

## Steps (for reference; skill.json is the source of truth)
1. Launch Mail app
2. Wait for window to appear
3. Open new message
4. Type recipient email
5. Click on subject field
6. Type email subject
7. Move to email body field
8. Type email body
