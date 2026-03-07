"""
window_manager.py — Win32 window control utilities.

Provides find, focus, minimize, maximize, and direct message-based
typing to windows — enabling background/headless automation without
keeping windows in the foreground.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _win32():
    """Lazy import win32 modules; raises ImportError if pywin32 not installed."""
    try:
        import win32gui
        import win32con
        import win32api
        return win32gui, win32con, win32api
    except ImportError:
        raise ImportError(
            "pywin32 is required for window management. "
            "Install: pip install pywin32"
        )


# ---------------------------------------------------------------------------
# Finding windows
# ---------------------------------------------------------------------------

def find_window(title_contains: str) -> Optional[int]:
    """
    Find a window whose title contains the given string (case-insensitive).

    Returns the window handle (hwnd) or None if not found.
    """
    win32gui, _, _ = _win32()
    results = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if title_contains.lower() in text.lower():
                results.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return results[0] if results else None


def list_windows() -> list[tuple[int, str]]:
    """Return list of (hwnd, title) for all visible windows."""
    win32gui, _, _ = _win32()
    results = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if text.strip():
                results.append((hwnd, text))

    win32gui.EnumWindows(callback, None)
    return sorted(results, key=lambda x: x[1].lower())


# ---------------------------------------------------------------------------
# Window state control
# ---------------------------------------------------------------------------

def focus_window(title_contains: str) -> bool:
    """
    Bring a window to the foreground by title.

    Returns True if window was found and focused.
    """
    win32gui, win32con, win32api = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        logger.warning("Window not found: '%s'", title_contains)
        return False

    # Restore if minimized
    placement = win32gui.GetWindowPlacement(hwnd)
    if placement[1] == win32con.SW_SHOWMINIMIZED:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.15)

    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.1)
    logger.debug("Focused window: '%s' (hwnd=%d)", title_contains, hwnd)
    return True


def minimize_window(title_contains: str) -> bool:
    """Minimize a window by title. Returns True if found."""
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        return False
    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    logger.debug("Minimized window: '%s'", title_contains)
    return True


def maximize_window(title_contains: str) -> bool:
    """Maximize a window by title. Returns True if found."""
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        return False
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    return True


def close_window(title_contains: str) -> bool:
    """Close a window by title. Returns True if found."""
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        return False
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    return True


# ---------------------------------------------------------------------------
# Background / headless typing
# ---------------------------------------------------------------------------

def type_to_window(title_contains: str, text: str) -> bool:
    """
    Send text directly to a window's edit control without needing focus.

    Works even when the window is minimized. Uses Win32 WM_CHAR messages
    sent directly to the edit control — bypasses PyAutoGUI entirely.

    Limitations:
      - Only works for standard Win32 edit controls (Notepad, most dialogs)
      - Does NOT work for modern UWP apps, browsers, or custom-rendered UIs
      - For those, use focus_window() first then normal typing

    Returns True if the edit control was found and text was sent.
    """
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        logger.warning("Window not found for background typing: '%s'", title_contains)
        return False

    # Find first child edit control
    edit_hwnd = win32gui.FindWindowEx(hwnd, None, "Edit", None)
    if edit_hwnd is None:
        logger.warning("No Edit control found in window: '%s'", title_contains)
        return False

    for char in text:
        win32gui.PostMessage(edit_hwnd, win32con.WM_CHAR, ord(char), 0)
        time.sleep(0.02)  # Small delay between chars for realism

    logger.debug("Background-typed %d chars to '%s'", len(text), title_contains)
    return True


def append_text_to_window(title_contains: str, text: str) -> bool:
    """
    Append text to an edit control by moving caret to end first.

    Returns True if successful.
    """
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        return False

    edit_hwnd = win32gui.FindWindowEx(hwnd, None, "Edit", None)
    if edit_hwnd is None:
        return False

    # Move caret to end
    win32gui.SendMessage(edit_hwnd, win32con.EM_SETSEL, -1, -1)
    # Append text char by char
    for char in text:
        win32gui.PostMessage(edit_hwnd, win32con.WM_CHAR, ord(char), 0)
        time.sleep(0.02)
    return True


def clear_window_text(title_contains: str) -> bool:
    """Clear all text in an edit control. Returns True if successful."""
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        return False
    edit_hwnd = win32gui.FindWindowEx(hwnd, None, "Edit", None)
    if edit_hwnd is None:
        return False
    win32gui.SetWindowText(edit_hwnd, "")
    return True


def get_window_text_content(title_contains: str) -> Optional[str]:
    """Read all text from an edit control. Returns None if window not found."""
    win32gui, win32con, _ = _win32()
    hwnd = find_window(title_contains)
    if hwnd is None:
        return None
    edit_hwnd = win32gui.FindWindowEx(hwnd, None, "Edit", None)
    if edit_hwnd is None:
        return win32gui.GetWindowText(hwnd)
    return win32gui.GetWindowText(edit_hwnd)
