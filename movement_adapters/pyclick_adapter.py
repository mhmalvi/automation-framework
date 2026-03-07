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

        if control_points:
            all_points = [start] + [tuple(map(int, p)) for p in control_points] + [end]
        else:
            all_points = self._auto_control_points(start, end)

        curve = self._bezier(all_points, self._PATH_STEPS)
        path = curve.as_points()
        self._execute_path(path, duration)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_bezier_path(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
    ) -> list:
        """Generate a Bezier path from start to end with auto control points."""
        points = self._auto_control_points(start, end)
        curve = self._bezier(points, self._PATH_STEPS)
        return curve.as_points()

    def _auto_control_points(
        self,
        start: Tuple[int, int],
        end: Tuple[int, int],
    ) -> List[Tuple[int, int]]:
        """
        Auto-generate control points that create a natural curved path.

        Applies perpendicular offsets scaled by distance to produce a gentle arc
        rather than a straight line. Adds slight asymmetry for realism.
        """
        import random
        import math

        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)

        # Perpendicular direction
        if distance > 0:
            perp_x = -dy / distance
            perp_y = dx / distance
        else:
            perp_x, perp_y = 0.0, 1.0

        # Control point spread proportional to distance
        spread = distance * random.uniform(0.2, 0.4)

        # Two control points at ~33% and ~66% along the path, offset perpendicularly
        cp1 = (
            int(start[0] + dx * 0.33 + perp_x * spread * random.uniform(0.5, 1.0)),
            int(start[1] + dy * 0.33 + perp_y * spread * random.uniform(0.5, 1.0)),
        )
        cp2 = (
            int(start[0] + dx * 0.66 + perp_x * spread * random.uniform(-1.0, -0.5)),
            int(start[1] + dy * 0.66 + perp_y * spread * random.uniform(-1.0, -0.5)),
        )
        return [start, cp1, cp2, end]

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
            from pyclick import HumanClicker, BezierCurve  # type: ignore[import]
            self._clicker = HumanClicker()
            self._bezier = BezierCurve
            logger.debug("pyclick adapter loaded successfully.")
        except ImportError:
            try:
                # Some versions only expose BezierCurve at top level
                from pyclick import BezierCurve  # type: ignore[import]
                self._bezier = BezierCurve
                self._clicker = object()  # sentinel for is_available
                logger.debug("pyclick (BezierCurve only) adapter loaded.")
            except ImportError:
                logger.debug(
                    "pyclick not installed. Adapter unavailable. "
                    "Install: pip install pyclick"
                )
        except Exception as exc:
            logger.warning("pyclick adapter init failed: %s", exc)
