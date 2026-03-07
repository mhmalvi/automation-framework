"""
input_controller.py — Unified input execution layer built on PyAutoGUI.

Accepts high-level commands (move, click, drag, type, hotkey) and executes
them through PyAutoGUI as the primary driver, with optional pydirectinput
fallback for games and DirectInput targets.

All methods integrate with the movement engine and behavior/typing engines
so that every action has natural human-like timing and motion.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

from core.movement_engine import MovementEngine
from utils.config_loader import get_config
from utils.timing_models import (
    ClickTimingProfile,
    PROFILE_FAST, PROFILE_NORMAL, PROFILE_CAUTIOUS,
    sleep_click_pre, sleep_click_hold, sleep_click_post,
    sleep_reaction_time,
)


logger = logging.getLogger(__name__)

# Profile name → dataclass mapping
_CLICK_PROFILES = {
    "fast": PROFILE_FAST,
    "normal": PROFILE_NORMAL,
    "cautious": PROFILE_CAUTIOUS,
}


class InputController:
    """
    Central execution layer for all keyboard and mouse actions.

    Wraps PyAutoGUI (primary) with optional pydirectinput fallback.
    Uses MovementEngine for realistic cursor trajectories and applies
    human-timing via the timing_models module.

    Example:
        ctrl = InputController()
        ctrl.move_and_click(400, 300)
        ctrl.type_text("Hello, world!")
        ctrl.hotkey("ctrl", "c")
    """

    def __init__(
        self,
        movement_engine: Optional[MovementEngine] = None,
        config_path: Optional[str] = None,
        use_direct_input: bool = False,
    ) -> None:
        """
        Args:
            movement_engine: Optional pre-built MovementEngine instance.
            config_path: Optional path to config file.
            use_direct_input: If True, prefer pydirectinput over pyautogui
                              where available (useful for DirectX applications).
        """
        self._cfg = get_config(config_path)
        self._engine = movement_engine or MovementEngine(config_path)
        self._use_direct_input = use_direct_input
        self._pyautogui = None
        self._pydirectinput = None
        self._click_profile = self._load_click_profile()
        self._init_backends()

    # ------------------------------------------------------------------
    # Mouse — movement
    # ------------------------------------------------------------------

    def move(
        self,
        x: float,
        y: float,
        duration: Optional[float] = None,
        react_first: bool = True,
    ) -> Tuple[float, float]:
        """
        Move cursor to (x, y) with human-like trajectory.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            duration: Travel duration override in seconds.
            react_first: Sleep a human reaction time before moving if True.

        Returns:
            (actual_x, actual_y) the cursor landed on.
        """
        if react_first:
            sleep_reaction_time()
        return self._engine.move(x, y, duration=duration)

    # ------------------------------------------------------------------
    # Mouse — clicks
    # ------------------------------------------------------------------

    def click(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        button: str = "left",
        move: bool = True,
    ) -> None:
        """
        Click at (x, y) with natural timing.

        Args:
            x: Target x. If None, clicks at current cursor position.
            y: Target y. If None, clicks at current cursor position.
            button: "left" | "right" | "middle".
            move: Move to target before clicking if True.
        """
        if x is not None and y is not None and move:
            self.move(x, y)

        sleep_click_pre(self._click_profile)
        self._backend_mouse_down(button)
        sleep_click_hold(self._click_profile)
        self._backend_mouse_up(button)
        sleep_click_post(self._click_profile)

        logger.debug("click(%s) at (%.0f, %.0f)", button, x or 0, y or 0)

    def double_click(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        button: str = "left",
    ) -> None:
        """
        Double-click at (x, y).

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            button: Mouse button to double-click.
        """
        self.click(x, y, button=button)
        # Short delay between clicks — typical human double-click interval
        import random
        time.sleep(random.uniform(0.04, 0.12))
        self.click(button=button, move=False)

    def right_click(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Right-click at (x, y). Convenience wrapper."""
        self.click(x, y, button="right")

    def move_and_click(self, x: float, y: float, button: str = "left") -> None:
        """Move to (x, y) then click. Most common action shorthand."""
        self.click(x, y, button=button, move=True)

    # ------------------------------------------------------------------
    # Mouse — drag
    # ------------------------------------------------------------------

    def drag(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        button: str = "left",
        duration: Optional[float] = None,
    ) -> None:
        """
        Drag from (start_x, start_y) to (end_x, end_y).

        Args:
            start_x: Drag start x.
            start_y: Drag start y.
            end_x: Drag end x.
            end_y: Drag end y.
            button: Mouse button to hold during drag.
            duration: Movement duration in seconds.
        """
        self.move(start_x, start_y)
        sleep_click_pre(self._click_profile)
        self._backend_mouse_down(button)

        # Move to end with button held — use moveTo (not dragTo, which does its
        # own mouseDown/mouseUp internally and would double-press the button)
        if self._pyautogui:
            drag_dur = duration or 0.4
            self._pyautogui.moveTo(
                int(end_x), int(end_y),
                duration=drag_dur,
            )
        else:
            self._engine.move(end_x, end_y, duration=duration)

        sleep_click_hold(self._click_profile)
        self._backend_mouse_up(button)
        logger.debug(
            "drag(%s) from (%.0f,%.0f) to (%.0f,%.0f)",
            button, start_x, start_y, end_x, end_y,
        )

    def scroll(self, x: float, y: float, clicks: int = 3, direction: str = "down") -> None:
        """
        Scroll at (x, y).

        Args:
            x: Scroll position x.
            y: Scroll position y.
            clicks: Number of scroll ticks.
            direction: "up" | "down".
        """
        self.move(x, y, react_first=False)
        scroll_amount = -clicks if direction == "down" else clicks
        if self._pyautogui:
            self._pyautogui.scroll(scroll_amount)
        logger.debug("scroll %s %d clicks at (%.0f,%.0f)", direction, clicks, x, y)

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def key_press(self, key: str) -> None:
        """
        Press and release a single key.

        Args:
            key: PyAutoGUI key name (e.g. "enter", "tab", "esc", "a").
        """
        if self._pyautogui:
            self._pyautogui.press(key)
        logger.debug("key_press(%s)", key)

    def hotkey(self, *keys: str) -> None:
        """
        Press a keyboard shortcut combination.

        Args:
            *keys: Key names in order (e.g. "ctrl", "c" for Ctrl+C).
        """
        if self._pyautogui:
            self._pyautogui.hotkey(*keys)
        logger.debug("hotkey(%s)", "+".join(keys))

    def type_text(self, text: str, interval: float = 0.0) -> None:
        """
        Type text using PyAutoGUI (raw, no human timing).

        For human-like typing, use TypingEngine.type() instead.

        Args:
            text: String to type.
            interval: Fixed inter-key interval (seconds). 0 = PyAutoGUI default.
        """
        if self._pyautogui:
            self._pyautogui.typewrite(text, interval=interval)

    def paste_text(self, text: str) -> None:
        """
        Copy text to clipboard and paste it (faster than typing long strings).

        Args:
            text: String to paste.
        """
        try:
            import pyperclip  # type: ignore[import]
            pyperclip.copy(text)
            self.hotkey("ctrl", "v")
            logger.debug("paste_text: %d chars via clipboard", len(text))
        except ImportError:
            logger.warning("pyperclip not installed; falling back to type_text")
            self.type_text(text)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def get_position(self) -> Tuple[int, int]:
        """Return current cursor (x, y) position."""
        if self._pyautogui:
            return self._pyautogui.position()
        return (0, 0)

    def set_click_profile(self, profile_name: str) -> None:
        """
        Switch click timing profile at runtime.

        Args:
            profile_name: "fast" | "normal" | "cautious".
        """
        if profile_name not in _CLICK_PROFILES:
            raise ValueError(f"Unknown profile '{profile_name}'. Options: {list(_CLICK_PROFILES)}")
        self._click_profile = _CLICK_PROFILES[profile_name]
        logger.info("Click profile set to: %s", profile_name)

    # ------------------------------------------------------------------
    # Backend helpers
    # ------------------------------------------------------------------

    def _init_backends(self) -> None:
        try:
            import pyautogui  # type: ignore[import]
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.0  # We manage timing ourselves
            self._pyautogui = pyautogui
            logger.debug("PyAutoGUI backend loaded.")
        except ImportError:
            logger.error(
                "PyAutoGUI is required. Install: pip install pyautogui"
            )

        if self._use_direct_input:
            try:
                import pydirectinput  # type: ignore[import]
                self._pydirectinput = pydirectinput
                logger.debug("pydirectinput backend loaded.")
            except ImportError:
                logger.debug("pydirectinput not installed; using PyAutoGUI only.")

    def _backend_mouse_down(self, button: str) -> None:
        """Press mouse button down."""
        if self._pydirectinput and self._use_direct_input:
            self._pydirectinput.mouseDown(button=button)
        elif self._pyautogui:
            self._pyautogui.mouseDown(button=button)

    def _backend_mouse_up(self, button: str) -> None:
        """Release mouse button."""
        if self._pydirectinput and self._use_direct_input:
            self._pydirectinput.mouseUp(button=button)
        elif self._pyautogui:
            self._pyautogui.mouseUp(button=button)

    def _load_click_profile(self) -> ClickTimingProfile:
        profile_name = self._cfg.get("behavior.click_profile", "normal")
        return _CLICK_PROFILES.get(profile_name, PROFILE_NORMAL)
