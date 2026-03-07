"""
human_mouse_adapter.py — Adapter wrapping the `human-mouse` library.

Library: https://github.com/sarperavci/human_mouse
Install: pip install human-mouse

Provides curved, interpolated cursor trajectories with acceleration and
micro-corrections. Falls back gracefully if the library is not installed.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.movement_engine import BaseMovementAdapter

logger = logging.getLogger(__name__)


class HumanMouseAdapter(BaseMovementAdapter):
    """
    Wraps the `human_mouse` library's HumanMouse class.

    The library generates realistic curved mouse paths using Bezier interpolation
    with configurable speed, smoothness, and random variation.
    """

    name = "human_mouse"

    def __init__(self) -> None:
        self._lib = None
        self._instance = None
        self._try_import()

    # ------------------------------------------------------------------
    # BaseMovementAdapter interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if human-mouse was successfully imported."""
        return self._lib is not None

    def move_to(self, x: float, y: float, duration: Optional[float] = None) -> None:
        """
        Move cursor to (x, y) using human_mouse curved trajectory.

        Args:
            x: Target x coordinate in pixels.
            y: Target y coordinate in pixels.
            duration: Ignored by this adapter — human_mouse controls speed
                      internally via its `speed` parameter set at init.
        """
        if not self.is_available():
            raise RuntimeError(
                "human-mouse library is not installed. Run: pip install human-mouse"
            )
        try:
            self._instance.move(int(x), int(y))
            logger.debug("human_mouse: moved to (%d, %d)", int(x), int(y))
        except Exception as exc:
            logger.error("human_mouse move_to failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Extended API (human_mouse-specific extras)
    # ------------------------------------------------------------------

    def click(self, x: float, y: float, button: str = "left") -> None:
        """
        Move to position and click using human_mouse.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            button: "left" | "right" | "middle".
        """
        if not self.is_available():
            raise RuntimeError("human-mouse library is not installed.")
        self.move_to(x, y)
        try:
            if button == "right":
                self._instance.perform_context_click(int(x), int(y))
            else:
                self._instance.perform_click(int(x), int(y))
        except Exception as exc:
            logger.error("human_mouse click failed: %s", exc)
            raise

    def drag_to(self, x: float, y: float) -> None:
        """
        Drag the cursor from its current position to (x, y).

        Args:
            x: Destination x coordinate.
            y: Destination y coordinate.
        """
        if not self.is_available():
            raise RuntimeError("human-mouse library is not installed.")
        try:
            self._instance.drag(int(x), int(y))
        except AttributeError:
            # Fallback: move while button held — handled by input_controller
            logger.warning("human_mouse drag not available; use input_controller.drag()")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _try_import(self) -> None:
        try:
            from human_mouse import MouseController  # type: ignore[import]
            self._lib = MouseController
            self._instance = MouseController()
            logger.debug("human_mouse adapter loaded successfully.")
        except ImportError:
            logger.debug(
                "human-mouse not installed. Adapter unavailable. "
                "Install: pip install human-mouse"
            )
        except Exception as exc:
            logger.warning("human_mouse adapter init failed: %s", exc)
