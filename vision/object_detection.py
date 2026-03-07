"""
object_detection.py — Screen-aware object localization for dynamic targets.

Provides higher-level detection strategies beyond simple template matching:
  - Color-based region detection
  - Contour-based shape detection
  - Text region detection (via PyTesseract if available)
  - Change detection between frames (useful for detecting UI transitions)

All methods return screen coordinates suitable for passing to MovementEngine.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from vision.screen_capture import ScreenCapture, Region

logger = logging.getLogger(__name__)

# Bounding box: (left, top, width, height)
BoundingBox = Tuple[int, int, int, int]
# Point: (x, y)
Point = Tuple[int, int]


class ObjectDetector:
    """
    Detects UI elements and regions on screen using OpenCV analysis.

    Use this when template matching isn't feasible (dynamic content, colored
    buttons, text regions) or when you need multiple candidate locations.

    Example:
        detector = ObjectDetector()
        # Find bright red regions (e.g., error buttons)
        regions = detector.find_by_color((0, 0, 200), (50, 50, 255))
        if regions:
            x, y, w, h = regions[0]
            center_x, center_y = x + w//2, y + h//2
    """

    def __init__(self, capture: Optional[ScreenCapture] = None) -> None:
        """
        Args:
            capture: Optional ScreenCapture instance. Creates new one if None.
        """
        self._capture = capture or ScreenCapture()
        self._cv2 = None
        self._init_cv2()

    # ------------------------------------------------------------------
    # Color-based detection
    # ------------------------------------------------------------------

    def find_by_color(
        self,
        lower_bgr: Tuple[int, int, int],
        upper_bgr: Tuple[int, int, int],
        region: Optional[Region] = None,
        min_area: int = 100,
        max_results: int = 10,
    ) -> List[BoundingBox]:
        """
        Find screen regions matching a BGR color range.

        Args:
            lower_bgr: Lower bound of BGR color range (e.g. (0, 0, 180) for red).
            upper_bgr: Upper bound of BGR color range.
            region: Optional screen area to search.
            min_area: Minimum pixel area to consider a valid match.
            max_results: Maximum number of bounding boxes to return.

        Returns:
            List of (left, top, width, height) bounding boxes, sorted by area desc.
        """
        self._require_cv2()
        frame = self._capture.capture(region)
        lower = np.array(lower_bgr, dtype=np.uint8)
        upper = np.array(upper_bgr, dtype=np.uint8)
        mask = self._cv2.inRange(frame, lower, upper)

        # Clean up noise
        kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (5, 5))
        mask = self._cv2.morphologyEx(mask, self._cv2.MORPH_CLOSE, kernel)
        mask = self._cv2.morphologyEx(mask, self._cv2.MORPH_OPEN, kernel)

        contours, _ = self._cv2.findContours(
            mask, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE
        )
        boxes: List[BoundingBox] = []
        for c in contours:
            area = self._cv2.contourArea(c)
            if area < min_area:
                continue
            x, y, w, h = self._cv2.boundingRect(c)
            if region:
                x += region[0]
                y += region[1]
            boxes.append((x, y, w, h))

        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        return boxes[:max_results]

    def find_by_color_hsv(
        self,
        lower_hsv: Tuple[int, int, int],
        upper_hsv: Tuple[int, int, int],
        region: Optional[Region] = None,
        min_area: int = 100,
    ) -> List[BoundingBox]:
        """
        Find regions matching an HSV color range (more robust to lighting).

        Args:
            lower_hsv: Lower HSV bound (H: 0-179, S: 0-255, V: 0-255).
            upper_hsv: Upper HSV bound.
            region: Optional screen region.
            min_area: Minimum pixel area.

        Returns:
            List of (left, top, width, height) bounding boxes.
        """
        self._require_cv2()
        frame = self._capture.capture(region)
        hsv = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2HSV)
        mask = self._cv2.inRange(
            hsv, np.array(lower_hsv, dtype=np.uint8), np.array(upper_hsv, dtype=np.uint8)
        )
        contours, _ = self._cv2.findContours(
            mask, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE
        )
        boxes = []
        for c in contours:
            if self._cv2.contourArea(c) >= min_area:
                x, y, w, h = self._cv2.boundingRect(c)
                if region:
                    x += region[0]
                    y += region[1]
                boxes.append((x, y, w, h))
        return boxes

    # ------------------------------------------------------------------
    # Shape/contour detection
    # ------------------------------------------------------------------

    def find_rectangles(
        self,
        region: Optional[Region] = None,
        min_area: int = 500,
        aspect_ratio_range: Tuple[float, float] = (0.2, 5.0),
        max_results: int = 15,
    ) -> List[BoundingBox]:
        """
        Detect rectangular regions (buttons, input fields, panels).

        Args:
            region: Optional capture region.
            min_area: Minimum bounding box area in pixels.
            aspect_ratio_range: (min, max) acceptable width/height ratios.
            max_results: Maximum rectangles to return.

        Returns:
            List of (left, top, width, height) bounding boxes.
        """
        self._require_cv2()
        gray = self._capture.capture_gray(region)
        blurred = self._cv2.GaussianBlur(gray, (5, 5), 0)
        edges = self._cv2.Canny(blurred, 30, 100)
        kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (3, 3))
        edges = self._cv2.dilate(edges, kernel, iterations=1)

        contours, _ = self._cv2.findContours(
            edges, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE
        )
        boxes = []
        for c in contours:
            if self._cv2.contourArea(c) < min_area:
                continue
            approx = self._cv2.approxPolyDP(c, 0.02 * self._cv2.arcLength(c, True), True)
            if len(approx) < 4:
                continue
            x, y, w, h = self._cv2.boundingRect(approx)
            aspect = w / max(h, 1)
            if not (aspect_ratio_range[0] <= aspect <= aspect_ratio_range[1]):
                continue
            if region:
                x += region[0]
                y += region[1]
            boxes.append((x, y, w, h))

        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        return boxes[:max_results]

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    def detect_change(
        self,
        frame_a: np.ndarray,
        frame_b: np.ndarray,
        threshold: int = 30,
        min_area: int = 200,
    ) -> List[BoundingBox]:
        """
        Detect regions that changed between two frames.

        Useful for detecting UI transitions, loading spinners, or new elements.

        Args:
            frame_a: First BGR frame (before).
            frame_b: Second BGR frame (after).
            threshold: Pixel difference threshold [0-255].
            min_area: Minimum changed area to report.

        Returns:
            List of (left, top, width, height) bounding boxes of changed regions.
        """
        self._require_cv2()
        gray_a = self._cv2.cvtColor(frame_a, self._cv2.COLOR_BGR2GRAY)
        gray_b = self._cv2.cvtColor(frame_b, self._cv2.COLOR_BGR2GRAY)
        diff = self._cv2.absdiff(gray_a, gray_b)
        _, mask = self._cv2.threshold(diff, threshold, 255, self._cv2.THRESH_BINARY)

        kernel = self._cv2.getStructuringElement(self._cv2.MORPH_RECT, (7, 7))
        mask = self._cv2.dilate(mask, kernel, iterations=2)
        contours, _ = self._cv2.findContours(
            mask, self._cv2.RETR_EXTERNAL, self._cv2.CHAIN_APPROX_SIMPLE
        )
        boxes = []
        for c in contours:
            if self._cv2.contourArea(c) >= min_area:
                boxes.append(self._cv2.boundingRect(c))
        return boxes

    # ------------------------------------------------------------------
    # Pixel inspection
    # ------------------------------------------------------------------

    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """
        Get the BGR color of a single pixel.

        Args:
            x: Screen x coordinate.
            y: Screen y coordinate.

        Returns:
            (B, G, R) tuple of uint8 values.
        """
        frame = self._capture.capture(region=(x, y, 1, 1))
        pixel = frame[0, 0]
        return int(pixel[0]), int(pixel[1]), int(pixel[2])

    def center_of_box(self, box: BoundingBox) -> Point:
        """
        Return the center (x, y) of a bounding box.

        Args:
            box: (left, top, width, height) bounding box.

        Returns:
            (center_x, center_y) point.
        """
        return box[0] + box[2] // 2, box[1] + box[3] // 2

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_cv2(self) -> None:
        try:
            import cv2  # type: ignore[import]
            self._cv2 = cv2
        except ImportError:
            logger.warning("OpenCV not installed. Install: pip install opencv-python")

    def _require_cv2(self) -> None:
        if self._cv2 is None:
            raise RuntimeError("OpenCV required. Install: pip install opencv-python")
