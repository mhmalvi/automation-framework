"""
vision_auto_click_demo.py — Demonstrates vision-driven automation.

Shows:
  - Fast screen capture via MSS
  - Template matching to locate a UI element
  - Color-based region detection
  - Rectangle detection (buttons/input fields)
  - Vision → movement pipeline (detect target → human-like click)
  - Change detection between two frames

Prerequisites:
  - pip install mss opencv-python
  - For template matching: provide a template image (or use the included
    example that captures a region and uses it as its own template).

Run: python examples/vision_auto_click_demo.py
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vision.screen_capture import ScreenCapture
from vision.template_matching import TemplateMatcher
from vision.object_detection import ObjectDetector
from core.behavior_engine import BehaviorEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")
logger = logging.getLogger("demo.vision")


def separator(label: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {label}")
    print("─" * 55)


def demo_screen_capture(cap: ScreenCapture) -> None:
    separator("Demo 1: Fast Screen Capture")

    if not cap.is_available:
        print("  [SKIP] MSS or OpenCV not installed.")
        return

    t0 = time.perf_counter()
    frame = cap.capture()
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"  Full screen captured in {elapsed:.1f}ms")
    print(f"  Frame shape: {frame.shape}  dtype: {frame.dtype}")

    w, h = cap.get_screen_size()
    print(f"  Screen size: {w}x{h}")

    # Capture a region
    region = (0, 0, 400, 300)
    t0 = time.perf_counter()
    region_frame = cap.capture(region)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  Region {region} captured in {elapsed:.1f}ms, shape: {region_frame.shape}")

    # Save screenshot
    cap.save(frame, "/tmp/demo_screenshot.png")
    print("  Screenshot saved to /tmp/demo_screenshot.png")


def demo_color_detection(detector: ObjectDetector) -> None:
    separator("Demo 2: Color-Based Region Detection")
    print("  Looking for bright-red regions on screen (BGR: 0,0,180 → 80,80,255)...")

    try:
        boxes = detector.find_by_color(
            lower_bgr=(0, 0, 180),
            upper_bgr=(80, 80, 255),
            min_area=200,
        )
        if boxes:
            print(f"  Found {len(boxes)} red region(s):")
            for i, box in enumerate(boxes[:3]):
                cx, cy = detector.center_of_box(box)
                print(f"    [{i+1}] BBox={box}  center=({cx},{cy})")
        else:
            print("  No red regions detected (expected if screen has no red UI elements).")

        # Also try HSV-based detection for green elements
        print("  Looking for green regions (HSV hue: 35-85)...")
        green_boxes = detector.find_by_color_hsv(
            lower_hsv=(35, 80, 80),
            upper_hsv=(85, 255, 255),
            min_area=300,
        )
        print(f"  Found {len(green_boxes)} green region(s).")
    except RuntimeError as e:
        print(f"  [SKIP] {e}")


def demo_rectangle_detection(detector: ObjectDetector) -> None:
    separator("Demo 3: Rectangle Detection (Buttons/Input Fields)")
    try:
        # Search in top portion of screen where toolbars/buttons usually are
        boxes = detector.find_rectangles(
            region=(0, 0, 1920, 200),
            min_area=800,
            aspect_ratio_range=(1.5, 8.0),
            max_results=5,
        )
        print(f"  Found {len(boxes)} rectangular UI elements in top 200px of screen.")
        for i, box in enumerate(boxes):
            cx, cy = detector.center_of_box(box)
            print(f"    [{i+1}] {box[2]}x{box[3]} at ({box[0]},{box[1]})  center=({cx},{cy})")
    except RuntimeError as e:
        print(f"  [SKIP] {e}")


def demo_template_matching(matcher: TemplateMatcher, cap: ScreenCapture) -> None:
    separator("Demo 4: Template Matching (Self-Reference Test)")

    if not cap.is_available:
        print("  [SKIP] Capture backend unavailable.")
        return

    # Capture a small region, save it, then find it on screen
    sample_region = (100, 100, 80, 60)
    try:
        sample_frame = cap.capture(sample_region)
        import cv2
        template_path = "/tmp/demo_template.png"
        cv2.imwrite(template_path, sample_frame)
        print(f"  Saved template from region {sample_region} to {template_path}")

        result = matcher.find(template_path, confidence=0.90)
        if result:
            x, y, conf = result
            print(f"  Template found at ({x}, {y}) with confidence {conf:.3f}")
        else:
            print("  Template not found (may need tuned confidence for display scaling).")

        # Multi-scale test
        result_ms = matcher.find_multiscale(template_path, scales=[0.9, 1.0, 1.1])
        if result_ms:
            print(f"  Multi-scale match: ({result_ms[0]}, {result_ms[1]}) conf={result_ms[2]:.3f}")

    except Exception as e:
        print(f"  [SKIP] Template matching error: {e}")


def demo_change_detection(detector: ObjectDetector, cap: ScreenCapture) -> None:
    separator("Demo 5: Change Detection Between Frames")

    if not cap.is_available:
        print("  [SKIP] Capture backend unavailable.")
        return

    try:
        print("  Capturing frame A...")
        frame_a = cap.capture()
        print("  Move your mouse around for 2 seconds...")
        time.sleep(2.0)
        print("  Capturing frame B...")
        frame_b = cap.capture()

        changed_boxes = detector.detect_change(frame_a, frame_b, threshold=25, min_area=500)
        print(f"  Detected {len(changed_boxes)} changed region(s) between frames.")
        for i, box in enumerate(changed_boxes[:3]):
            print(f"    [{i+1}] Changed area: {box[2]}x{box[3]} at ({box[0]},{box[1]})")
    except Exception as e:
        print(f"  [SKIP] Change detection error: {e}")


def demo_vision_driven_click(
    detector: ObjectDetector,
    behavior: BehaviorEngine,
) -> None:
    separator("Demo 6: Vision → Human-Like Click Pipeline")

    try:
        print("  Detecting clickable rectangles on screen...")
        boxes = detector.find_rectangles(min_area=1000, max_results=3)
        if not boxes:
            print("  No rectangles found. Skipping vision-driven click.")
            return

        target_box = boxes[0]
        cx, cy = detector.center_of_box(target_box)
        print(f"  Target: {target_box[2]}x{target_box[3]} rect at center ({cx},{cy})")
        print("  Performing human-like click via BehaviorEngine...")
        behavior.human_click(cx, cy)
        print("  ✓ Vision-driven click executed.")
    except Exception as e:
        print(f"  [SKIP] Vision-click error: {e}")


def main() -> None:
    print("=" * 60)
    print("  Vision Auto-Click Demo — Screen Awareness + Human Motion")
    print("=" * 60)

    cap = ScreenCapture()
    matcher = TemplateMatcher(capture=cap)
    detector = ObjectDetector(capture=cap)
    behavior = BehaviorEngine()

    demo_screen_capture(cap)
    demo_color_detection(detector)
    demo_rectangle_detection(detector)
    demo_template_matching(matcher, cap)
    demo_change_detection(detector, cap)
    demo_vision_driven_click(detector, behavior)

    print("\n✓ Vision auto-click demo complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    except Exception as e:
        logger.error("Demo failed: %s", e)
        raise
