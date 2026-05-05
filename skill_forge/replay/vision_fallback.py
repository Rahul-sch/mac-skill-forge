"""Stub for the v0.2 vision fallback. Don't add OpenCV pixel matching here —
that's a v0.2 lever. The deterministic AX path is the v0 contract."""

from __future__ import annotations


def fallback(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
    raise NotImplementedError("vision fallback ships in v0.2")
