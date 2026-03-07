"""
template_matching.py — OpenCV-based template matching for UI element detection.

Finds a template image within a screenshot and returns the best match
location and confidence score. Supports grayscale and multi-scale matching.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from utils.config_loader import get_config
from vision.screen_capture import ScreenCapture, Region

logger = logging.getLogger(__name__)

# Match result: (center_x, center_y, confidence)
MatchResult = Tuple[int, int, float]


class TemplateMatcher:
    """
    Locates template images within screen captures using OpenCV TM_CCOEFF_NORMED.

    Supports:
      - Single best-match lookup
      - All-matches above confidence threshold
      - Multi-scale matching (handles DPI scaling differences)

    Example:
        matcher = TemplateMatcher()
        result = matcher.find("button.png")
        if result:
            x, y, confidence = result
            print(f"Found at ({x}, {y}) with confidence {confidence:.2f}")
    """

    def __init__(
        self,
        capture: Optional[ScreenCapture] = None,
        config_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            capture: Optional ScreenCapture instance.
            config_path: Optional config file path.
        """
        self._cfg = get_config(config_path)
        self._capture = capture or ScreenCapture()
        self._cv2 = None
        self._default_confidence = self._cfg.get("vision.match_confidence", 0.85)
        self._grayscale = self._cfg.get("vision.grayscale_matching", True)
        self._init_cv2()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find(
        self,
        template_path: str,
        region: Optional[Region] = None,
        confidence: Optional[float] = None,
        grayscale: Optional[bool] = None,
    ) -> Optional[MatchResult]:
        """
        Find the best match of a template image on screen.

        Args:
            template_path: Path to the template image file.
            region: Optional screen region to search within.
            confidence: Minimum confidence threshold [0–1]. Uses config default
                        if not specified.
            grayscale: Use grayscale matching if True. Faster but less accurate
                       for color-sensitive elements.

        Returns:
            (center_x, center_y, confidence) if found, None otherwise.
        """
        self._require_cv2()
        threshold = confidence if confidence is not None else self._default_confidence
        use_gray = grayscale if grayscale is not None else self._grayscale

        template = self._load_template(template_path, grayscale=use_gray)
        if template is None:
            return None

        screen = self._capture.capture_gray(region) if use_gray else self._capture.capture(region)
        result = self._cv2.matchTemplate(screen, template, self._cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = self._cv2.minMaxLoc(result)

        if max_val < threshold:
            logger.debug(
                "Template '%s' not found. Best confidence: %.3f (threshold: %.3f)",
                template_path, max_val, threshold,
            )
            return None

        h, w = template.shape[:2]
        cx = max_loc[0] + w // 2
        cy = max_loc[1] + h // 2

        # Adjust coordinates if a region offset was applied
        if region:
            cx += region[0]
            cy += region[1]

        logger.debug("Template '%s' found at (%d, %d) conf=%.3f", template_path, cx, cy, max_val)
        return cx, cy, max_val

    def find_all(
        self,
        template_path: str,
        region: Optional[Region] = None,
        confidence: Optional[float] = None,
        max_results: int = 20,
    ) -> List[MatchResult]:
        """
        Find all non-overlapping instances of a template on screen.

        Args:
            template_path: Path to template image.
            region: Optional screen region.
            confidence: Minimum confidence. Defaults to config value.
            max_results: Maximum number of results to return.

        Returns:
            List of (center_x, center_y, confidence) tuples, sorted by
            confidence descending.
        """
        self._require_cv2()
        threshold = confidence if confidence is not None else self._default_confidence

        template = self._load_template(template_path, grayscale=self._grayscale)
        if template is None:
            return []

        screen = (
            self._capture.capture_gray(region)
            if self._grayscale
            else self._capture.capture(region)
        )
        result = self._cv2.matchTemplate(screen, template, self._cv2.TM_CCOEFF_NORMED)

        locations = np.where(result >= threshold)
        h, w = template.shape[:2]
        matches: List[MatchResult] = []

        for pt in zip(*locations[::-1]):  # zip col, row
            cx = pt[0] + w // 2
            cy = pt[1] + h // 2
            conf = float(result[pt[1], pt[0]])
            if region:
                cx += region[0]
                cy += region[1]
            matches.append((cx, cy, conf))

        # Non-maximum suppression: remove overlapping detections
        matches = self._nms(matches, w, h)
        matches.sort(key=lambda m: m[2], reverse=True)
        return matches[:max_results]

    def find_multiscale(
        self,
        template_path: str,
        scales: Optional[List[float]] = None,
        region: Optional[Region] = None,
        confidence: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """
        Find template using multi-scale matching (handles zoom/DPI differences).

        Args:
            template_path: Path to template image.
            scales: List of scale factors to try. Defaults to [0.8, 0.9, 1.0, 1.1, 1.2].
            region: Optional screen region.
            confidence: Minimum confidence threshold.

        Returns:
            (center_x, center_y, confidence) of best match, or None.
        """
        self._require_cv2()
        scale_range = scales or [0.8, 0.9, 1.0, 1.1, 1.2]
        threshold = confidence if confidence is not None else self._default_confidence

        template_orig = self._load_template(template_path, grayscale=True)
        if template_orig is None:
            return None

        screen = self._capture.capture_gray(region)
        best: Optional[MatchResult] = None

        for scale in scale_range:
            h = max(1, int(template_orig.shape[0] * scale))
            w = max(1, int(template_orig.shape[1] * scale))
            resized = self._cv2.resize(template_orig, (w, h))

            if resized.shape[0] > screen.shape[0] or resized.shape[1] > screen.shape[1]:
                continue

            result = self._cv2.matchTemplate(screen, resized, self._cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = self._cv2.minMaxLoc(result)

            if max_val >= threshold and (best is None or max_val > best[2]):
                cx = max_loc[0] + w // 2
                cy = max_loc[1] + h // 2
                if region:
                    cx += region[0]
                    cy += region[1]
                best = (cx, cy, max_val)

        return best

    def wait_for(
        self,
        template_path: str,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
        region: Optional[Region] = None,
        confidence: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """
        Wait until a template appears on screen or timeout expires.

        Args:
            template_path: Path to template image.
            timeout: Maximum seconds to wait.
            poll_interval: How often to check (seconds).
            region: Optional screen region.
            confidence: Minimum confidence threshold.

        Returns:
            MatchResult when found, None on timeout.
        """
        import time
        deadline = time.time() + timeout
        while time.time() < deadline:
            result = self.find(template_path, region=region, confidence=confidence)
            if result:
                return result
            time.sleep(poll_interval)
        logger.debug("Timeout waiting for template: %s", template_path)
        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_template(self, path: str, grayscale: bool = True) -> Optional[np.ndarray]:
        """Load a template image from disk."""
        p = Path(path)
        if not p.exists():
            logger.error("Template image not found: %s", path)
            return None
        flag = self._cv2.IMREAD_GRAYSCALE if grayscale else self._cv2.IMREAD_COLOR
        img = self._cv2.imread(str(p), flag)
        if img is None:
            logger.error("Failed to load template image: %s", path)
        return img

    def _nms(
        self,
        matches: List[MatchResult],
        template_w: int,
        template_h: int,
    ) -> List[MatchResult]:
        """Simple non-maximum suppression to deduplicate overlapping matches."""
        kept: List[MatchResult] = []
        half_w = template_w // 2
        half_h = template_h // 2

        for m in matches:
            is_dup = any(
                abs(m[0] - k[0]) < half_w and abs(m[1] - k[1]) < half_h
                for k in kept
            )
            if not is_dup:
                kept.append(m)
        return kept

    def _init_cv2(self) -> None:
        try:
            import cv2  # type: ignore[import]
            self._cv2 = cv2
        except ImportError:
            logger.warning("OpenCV not installed. Install: pip install opencv-python")

    def _require_cv2(self) -> None:
        if self._cv2 is None:
            raise RuntimeError("OpenCV required. Install: pip install opencv-python")
