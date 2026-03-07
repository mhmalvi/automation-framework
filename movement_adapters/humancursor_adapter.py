"""
humancursor_adapter.py — Adapter wrapping the `humancursor` library.

Library: https://github.com/riflosnake/HumanCursor
Install: pip install humancursor

Implements natural system cursor control patterns including smooth movement,
random deviation, and realistic speed profiles based on Fitts's Law.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.movement_engine import BaseMovementAdapter

logger = logging.getLogger(__name__)


class HumanCursorAdapter(BaseMovementAdapter):
    """
    Wraps the HumanCursor library's SystemCursor for realistic motion.

    HumanCursor uses a physics-inspired model that accounts for target size and
    distance (Fitts's Law) to determine movement speed and path complexity.
    It also includes built-in randomization for natural feel.
    """

    name = "humancursor"

    def __init__(self) -> None:
        self._cursor = None
        self._try_import()

    # ------------------------------------------------------------------
    # BaseMovementAdapter interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if humancursor was successfully imported."""
        return self._cursor is not None

    def move_to(self, x: float, y: float, duration: Optional[float] = None) -> None:
        """
        Move cursor to (x, y) using HumanCursor's natural control pattern.

        Args:
            x: Target x coordinate in pixels.
            y: Target y coordinate in pixels.
            duration: Not directly used — HumanCursor manages speed internally.
                      If provided, sets a gross speed multiplier hint.
        """
        if not self.is_available():
            raise RuntimeError(
                "humancursor library is not installed. Run: pip install humancursor"
            )
        try:
            # HumanCursor.move_to() performs Fitts's Law-based natural movement
            self._cursor.move_to([int(x), int(y)])
            logger.debug("humancursor: moved to (%d, %d)", int(x), int(y))
        except Exception as exc:
            logger.error("humancursor move_to failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Extended API (humancursor-specific extras)
    # ------------------------------------------------------------------

    def click(self, x: float, y: float, button: str = "left") -> None:
        """
        Move to position and click using HumanCursor.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            button: "left" | "right" | "middle".
        """
        if not self.is_available():
            raise RuntimeError("humancursor is not installed.")
        self.move_to(x, y)
        try:
            self._cursor.click([int(x), int(y)], button=button)
        except TypeError:
            self._cursor.click([int(x), int(y)])

    def move_relative(self, dx: float, dy: float) -> None:
        """
        Move the cursor by a relative offset from its current position.

        Args:
            dx: Horizontal offset in pixels (positive = right).
            dy: Vertical offset in pixels (positive = down).
        """
        if not self.is_available():
            raise RuntimeError("humancursor is not installed.")
        try:
            import pyautogui  # type: ignore[import]
            current_x, current_y = pyautogui.position()
            self.move_to(current_x + dx, current_y + dy)
        except ImportError:
            logger.error("pyautogui required for move_relative; pip install pyautogui")
            raise

    def idle_flick(self, radius: float = 30.0) -> None:
        """
        Perform a small random idle movement (simulates human fidgeting).

        Args:
            radius: Maximum pixel radius of the random flick.
        """
        import random
        import math
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(5, radius)
        dx = r * math.cos(angle)
        dy = r * math.sin(angle)
        self.move_relative(dx, dy)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _try_import(self) -> None:
        try:
            from humancursor import SystemCursor  # type: ignore[import]
            self._cursor = SystemCursor()
            logger.debug("humancursor adapter loaded successfully.")
        except ImportError:
            logger.debug(
                "humancursor not installed. Adapter unavailable. "
                "Install: pip install humancursor"
            )
        except Exception as exc:
            logger.warning("humancursor adapter init failed: %s", exc)
