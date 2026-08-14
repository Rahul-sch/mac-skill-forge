"""macOS permission probes for Accessibility and Screen Recording."""

from __future__ import annotations


def accessibility_granted() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return False
    return bool(AXIsProcessTrusted())


def screen_recording_granted() -> bool:
    """Check Screen Recording without prompting when the preflight API exists."""
    try:
        import Quartz
    except ImportError:
        return False

    preflight = getattr(Quartz, "CGPreflightScreenCaptureAccess", None)
    if preflight is not None:
        return bool(preflight())
    rect = Quartz.CGRectMake(0, 0, 1, 1)
    image = Quartz.CGWindowListCreateImage(
        rect,
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault,
    )
    if image is None:
        return False
    width = Quartz.CGImageGetWidth(image)
    return width > 0


def input_monitoring_granted() -> bool:
    """Return whether global input listening is permitted on this macOS version."""
    try:
        import Quartz
    except ImportError:
        return False
    preflight = getattr(Quartz, "CGPreflightListenEventAccess", None)
    if preflight is None:
        return accessibility_granted()
    return bool(preflight())
