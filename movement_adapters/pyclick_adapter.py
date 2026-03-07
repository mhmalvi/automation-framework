"""
pyclick_adapter.py — Adapter wrapping the `pyclick` library.

Library: https://github.com/patrikoss/pyclick
Install: pip install pyclick

Uses Bezier curves with configurable control points to generate smooth,
human-like cursor trajectories with natural speed profiles.
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

from core.movement_engine import BaseMovementAdapter

logger = logging.getLogger(__name__)


class PyClickAdapter(BaseMovementAdapter):
    """
    Wraps PyClick's HumanClicker and BezierCurve for mouse movement.

    PyClick provides a BezierCurve class to generate smooth paths between
    points and a HumanClicker that executes those paths via pyautogui.
    """

    name = "pyclick"

    # Number of Bezier control points to generate realistic curves
    _NUM_CONTROL_POINTS = 4
    # Steps in the interpolated path
    _PATH_STEPS = 100

    def __init__(self) -> None:
        self._clicker = None
        self._bezier = None
        self._pyautogui = None
        self._try_import()

    # ------------------------------------------------------------------
    # BaseMovementAdapter interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if pyclick was successfully imported."""
        return self._clicker is not None

    def move_to(self, x: float, y: float, duration: Optional[float] = None) -> None:
        """
        Move cursor to (x, y) using a Bezier curve path.

        Args:
            x: Target x coordinate in pixels.
            y: Target y coordinate in pixels.
            duration: Total movement duration in seconds. Defaults to 0.5s.
        """
        if not self.is_available():
            raise RuntimeError(
                "pyclick library is not installed. Run: pip install pyclick"
            )

        move_duration = duration if duration is not None else 0.5

        try:
            import pyautogui  # type: ignore[import]
            current_x, current_y = pyautogui.position()
            path = self._generate_bezier_path(
                (current_x, current_y), (int(x), int(y))
            )
            self._execute_path(path, move_duration)
            logger.debug("pyclick: moved to (%d, %d) in %.2fs", int(x), int(y), move_duration)
        except Exception as exc:
            logger.error("pyclick move_to failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Extended API
    # ------------------------------------------------------------------

    def move_with_control_points(
        self,
        x: float,
        y: float,
        control_points: Optional[List[Tuple[float, float]]] = None,
        duration: float = 0.5,
    ) -> None:
        """
        Move to (x, y) using explicit Bezier control points.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            control_points: List of (x, y) intermediate control points.
                            If None, control points are auto-generated.
            duration: Movement duration in seconds.
        """
        if not self.is_available():
            raise RuntimeError("pyclick is not installed.")
        import pyautogui  # type: ignore[import]
        current_x, current_y = pyautogui.position()
        start = (current_x, current_y)
        end = (int(x), int(y))

        curve = self._bezier(start, end)
        path = curve.points
        self._execute_path(path, duration)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_bezier_path(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
    ) -> list:
        """Generate a HumanCurve path from start to end."""
        curve = self._bezier(start, end)
        return curve.points

    def _execute_path(self, path: list, duration: float) -> None:
        """Execute a list of (x, y) positions as a smooth cursor movement."""
        import pyautogui  # type: ignore[import]
        if not path:
            return
        interval = duration / max(len(path) - 1, 1)
        for point in path:
            pyautogui.moveTo(int(point[0]), int(point[1]), duration=0)
            if interval > 0:
                time.sleep(interval)

    def _try_import(self) -> None:
        try:
            from pyclick import HumanClicker, HumanCurve  # type: ignore[import]
            self._clicker = HumanClicker()
            self._bezier = HumanCurve
            logger.debug("pyclick adapter loaded successfully.")
        except ImportError:
            logger.debug(
                "pyclick not installed. Adapter unavailable. "
                "Install: pip install pyclick"
            )
        except Exception as exc:
            logger.warning("pyclick adapter init failed: %s", exc)
