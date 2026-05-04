"""macOS permission probes for Accessibility and Screen Recording."""

from __future__ import annotations


def accessibility_granted() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted
    except ImportError:
        return False
    return bool(AXIsProcessTrusted())


def screen_recording_granted() -> bool:
    """Probe Screen Recording by attempting a 1x1 capture of the main display.

    On first call macOS will prompt the user. Subsequent calls return immediately.
    """
    try:
        import Quartz
    except ImportError:
        return False

    main_display_id = Quartz.CGMainDisplayID()
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
    _ = main_display_id
    return width > 0
