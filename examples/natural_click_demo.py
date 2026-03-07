"""
natural_click_demo.py — Demonstrates human-like cursor movement and clicking.

Shows:
  - Adapter selection and fallback chain reporting
  - Curved trajectories to multiple targets
  - Overshoot and self-correction behavior
  - Idle micro-flicks
  - Click timing variability

Run: python examples/natural_click_demo.py
"""

import sys
import time
import logging
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.behavior_engine import BehaviorEngine
from core.movement_engine import MovementEngine
from utils.config_loader import get_config

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s  %(name)s: %(message)s")
logger = logging.getLogger("demo.natural_click")


def main() -> None:
    print("=" * 60)
    print("  Natural Click Demo — Human-Like Cursor Movement")
    print("=" * 60)
    print("WARNING: This demo will move your cursor. Press Ctrl+C to stop.")
    print("Starting in 3 seconds...")
    time.sleep(3)

    # ---- Setup --------------------------------------------------------
    cfg = get_config()
    engine = MovementEngine()

    print(f"\n[Config] adapter mode : {cfg.movement_adapter()}")
    print(f"[Config] fallback chain: {cfg.fallback_chain()}")
    print(f"[Active] adapter       : {engine.active_adapter.name if engine.active_adapter else 'NONE'}")
    print(f"[Active] all available : {engine.available_adapters}\n")

    behavior = BehaviorEngine()

    # ---- Demo 1: Simple move-and-click sequence -----------------------
    targets = [
        (200, 200, "top-left area"),
        (800, 400, "center-right area"),
        (400, 600, "bottom-center area"),
        (100, 500, "left side"),
    ]

    print("[Demo 1] Moving to multiple targets with natural trajectories...")
    for x, y, label in targets:
        print(f"  → Moving to {label} ({x}, {y})")
        actual_x, actual_y = engine.move(x, y, duration=0.6)
        print(f"    Landed at ({actual_x:.1f}, {actual_y:.1f}) [jitter applied]")
        time.sleep(0.4)

    # ---- Demo 2: Human-like clicks ------------------------------------
    print("\n[Demo 2] Performing human-like clicks (normal profile)...")
    click_spots = [(300, 300), (600, 300), (600, 500), (300, 500)]
    for x, y in click_spots:
        print(f"  → Clicking ({x}, {y})")
        behavior.human_click(x, y)
        time.sleep(0.3)

    # ---- Demo 3: Hesitation click (like reading before clicking) ------
    print("\n[Demo 3] Hesitation click (simulating 'thinking' before clicking)...")
    behavior.think_pause(complexity=1.5)
    behavior.human_click(500, 400, hesitate=True)
    print("  ✓ Hesitation click done")

    # ---- Demo 4: Adapter switching ------------------------------------
    print("\n[Demo 4] Switching adapters at runtime...")
    for adapter_name in engine.available_adapters:
        print(f"  → Switching to: {adapter_name}")
        engine.set_adapter(adapter_name)
        actual_x, actual_y = engine.move(400, 300)
        print(f"    Moved to ({actual_x:.1f}, {actual_y:.1f}) via {adapter_name}")
        time.sleep(0.5)

    # Restore to "all" mode
    engine.set_adapter("all")

    # ---- Demo 5: Right-click (uses hesitation internally) -------------
    print("\n[Demo 5] Right-click with natural hesitation...")
    behavior.human_right_click(450, 350)
    time.sleep(0.3)
    # Dismiss the context menu
    behavior.human_key_press("escape")

    print("\n✓ Natural click demo complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    except Exception as e:
        logger.error("Demo failed: %s", e)
        raise
