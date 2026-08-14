from __future__ import annotations

from email.message import Message

from landing.server import request_is_authorized


def _headers(token: str, origin: str | None = None) -> Message:
    headers = Message()
    headers["X-Skill-Forge-Token"] = token
    if origin:
        headers["Origin"] = origin
    return headers


def test_demo_authorization_requires_exact_token():
    assert request_is_authorized(_headers("secret"), "secret")
    assert not request_is_authorized(_headers("wrong"), "secret")
    assert not request_is_authorized(Message(), "secret")


def test_demo_authorization_rejects_remote_browser_origin():
    assert request_is_authorized(_headers("secret", "http://127.0.0.1:8000"), "secret")
    assert request_is_authorized(_headers("secret", "http://localhost:8000"), "secret")
    assert not request_is_authorized(_headers("secret", "https://evil.example"), "secret")
