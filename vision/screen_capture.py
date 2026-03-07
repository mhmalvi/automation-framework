"""
screen_capture.py — Fast screen capture using MSS with OpenCV integration.

Provides single-frame and continuous capture with optional region cropping.
All captures are returned as NumPy arrays compatible with OpenCV functions.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    _NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Type alias for a capture region: (left, top, width, height)
Region = Tuple[int, int, int, int]


class ScreenCapture:
    """
    Fast screenshot utility using MSS (multiple screen shots).

    MSS is significantly faster than PyAutoGUI's screenshot because it
    uses low-level OS APIs and avoids PIL intermediate conversions.

    Example:
        cap = ScreenCapture()
        frame = cap.capture()                   # full screen as BGR ndarray
        region = cap.capture(region=(0,0,800,600))  # top-left 800x600
        gray = cap.capture_gray()               # grayscale full screen
    """

    def __init__(self, monitor_index: int = 1) -> None:
        """
        Args:
            monitor_index: MSS monitor index. 1 = primary monitor, 0 = all monitors.
        """
        self._monitor_index = monitor_index
        self._mss = None
        self._cv2 = None
        self._init()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(self, region: Optional[Region] = None) -> np.ndarray:
        """
        Capture the screen or a region, returned as a BGR NumPy array.

        Args:
            region: Optional (left, top, width, height) bounding box.
                    If None, captures the full monitor.

        Returns:
            BGR uint8 NumPy array with shape (height, width, 3).

        Raises:
            RuntimeError: If MSS or OpenCV is not installed.
        """
        self._require_backends()

        with self._mss_lib.mss() as sct:
            monitor = self._get_monitor(sct, region)
            raw = sct.grab(monitor)
            # MSS returns BGRA; drop alpha channel for OpenCV compatibility
            frame = np.array(raw)[:, :, :3]
            return frame

    def capture_gray(self, region: Optional[Region] = None) -> np.ndarray:
        """
        Capture screen and convert to grayscale.

        Args:
            region: Optional capture region.

        Returns:
            Grayscale uint8 NumPy array with shape (height, width).
        """
        frame = self.capture(region)
        return self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)

    def capture_rgb(self, region: Optional[Region] = None) -> np.ndarray:
        """
        Capture screen as RGB (channel order: R, G, B).

        Args:
            region: Optional capture region.

        Returns:
            RGB uint8 NumPy array with shape (height, width, 3).
        """
        frame = self.capture(region)
        return self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)

    def get_screen_size(self) -> Tuple[int, int]:
        """
        Return the primary monitor's (width, height) in pixels.

        Returns:
            (width, height) tuple.
        """
        self._require_backends()
        with self._mss_lib.mss() as sct:
            m = sct.monitors[self._monitor_index]
            return m["width"], m["height"]

    def crop(self, frame: np.ndarray, region: Region) -> np.ndarray:
        """
        Crop a NumPy frame to the given region.

        Args:
            frame: Full-screen BGR array.
            region: (left, top, width, height) to crop.

        Returns:
            Cropped BGR array.
        """
        left, top, width, height = region
        return frame[top:top + height, left:left + width]

    def save(self, frame: np.ndarray, path: str) -> None:
        """
        Save a captured frame to disk.

        Args:
            frame: BGR NumPy array to save.
            path: Output file path (e.g. "screenshot.png").
        """
        self._require_backends()
        self._cv2.imwrite(path, frame)
        logger.debug("Screenshot saved to: %s", path)

    @property
    def is_available(self) -> bool:
        """Return True if both MSS and OpenCV are installed."""
        return self._mss_lib is not None and self._cv2 is not None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init(self) -> None:
        self._mss_lib = None
        self._cv2 = None
        try:
            import mss  # type: ignore[import]
            self._mss_lib = mss
            logger.debug("MSS loaded.")
        except ImportError:
            logger.warning("MSS not installed. Run: pip install mss")

        try:
            import cv2  # type: ignore[import]
            self._cv2 = cv2
            logger.debug("OpenCV loaded.")
        except ImportError:
            logger.warning("OpenCV not installed. Run: pip install opencv-python")

    def _require_backends(self) -> None:
        if not _NUMPY_AVAILABLE:
            raise RuntimeError("NumPy is required. Install: pip install numpy")
        if self._mss_lib is None:
            raise RuntimeError("MSS is required. Install: pip install mss")
        if self._cv2 is None:
            raise RuntimeError("OpenCV is required. Install: pip install opencv-python")

    def _get_monitor(self, sct, region: Optional[Region]) -> dict:
        """Build MSS monitor dict from region or use full monitor."""
        if region:
            left, top, width, height = region
            return {"left": left, "top": top, "width": width, "height": height}
        return sct.monitors[self._monitor_index]
