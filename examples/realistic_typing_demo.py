"""
realistic_typing_demo.py — Demonstrates human-like typing simulation.

Shows:
  - Variable keystroke intervals (normal, fast, slow profiles)
  - Burst typing sequences
  - Mid-word hesitation pauses
  - Typo injection with realistic backspace correction
  - Word-by-word typing mode
  - Clipboard paste for long text

Open a text editor before running so typed text appears.
Run: python examples/realistic_typing_demo.py
"""

import sys
import time
import logging

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.typing_engine import TypingEngine
from core.behavior_engine import BehaviorEngine
from utils.config_loader import get_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")
logger = logging.getLogger("demo.typing")


def separator(label: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {label}")
    print("─" * 50)


def main() -> None:
    print("=" * 60)
    print("  Realistic Typing Demo — Human-Like Keyboard Simulation")
    print("=" * 60)
    print("Open a text editor (e.g. Notepad) and click into it.")
    print("Starting in 5 seconds...")
    time.sleep(5)

    typer = TypingEngine()
    behavior = BehaviorEngine()

    # ---- Demo 1: Normal typing profile --------------------------------
    separator("Demo 1: Normal typing (variable intervals + occasional bursts)")
    behavior.human_key_press("enter")
    typer.type("This is normal-speed typing with natural variation in keystroke timing.")
    time.sleep(1.0)

    # ---- Demo 2: Fast typing profile ----------------------------------
    separator("Demo 2: Fast typing (professional typist simulation)")
    behavior.human_key_press("enter")
    typer.type(
        "Fast typing mode: high burst probability, shorter intervals.",
        profile_name="fast",
    )
    time.sleep(1.0)

    # ---- Demo 3: Slow/cautious typing ---------------------------------
    separator("Demo 3: Slow typing (hunt-and-peck style)")
    behavior.human_key_press("enter")
    typer.type(
        "Slow typing... with longer pauses... and more hesitation.",
        profile_name="slow",
    )
    time.sleep(1.5)

    # ---- Demo 4: Typo injection with correction -----------------------
    separator("Demo 4: Typo + correction (enabled explicitly)")
    behavior.human_key_press("enter")
    # Force typo probability high to guarantee demonstration
    from utils.timing_models import TypingTimingProfile
    typo_profile = TypingTimingProfile(
        base_interval_mean=0.13,
        typo_probability=0.15,  # 15% chance per alpha char for demo
        correction_delay_mean=0.4,
    )
    typer._profile = typo_profile
    typer.type("Watch for typos being corrected automatically as you type.")
    # Restore normal profile
    typer._profile = typer._load_profile()
    time.sleep(1.5)

    # ---- Demo 5: Word-by-word typing ----------------------------------
    separator("Demo 5: Word-by-word mode (micro-pauses at word boundaries)")
    behavior.human_key_press("enter")
    typer.type_word_by_word(
        "Each word is typed with a small pause between them.",
        word_pause_mean=0.12,
    )
    time.sleep(1.0)

    # ---- Demo 6: Typing with explicit hesitations ---------------------
    separator("Demo 6: Hesitation at specific positions (composing a sentence)")
    behavior.human_key_press("enter")
    text = "Let me think... about this sentence before I finish it."
    # Hesitate at position 14 ("about") and 37 ("finish")
    typer.type_with_hesitation(text, hesitation_positions=[14, 37])
    time.sleep(1.0)

    # ---- Demo 7: Long text via clipboard paste ------------------------
    separator("Demo 7: Long text pasted via clipboard (exceeds paste threshold)")
    behavior.human_key_press("enter")
    long_text = (
        "This is a much longer block of text that exceeds the clipboard paste threshold "
        "configured in the framework. Instead of typing each character, the engine copies "
        "this to the clipboard and pastes it instantly — mimicking how a human would paste "
        "pre-written content rather than type it all out character by character."
    )
    typer.type(long_text)
    time.sleep(1.0)

    print("\n✓ Realistic typing demo complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    except Exception as e:
        logger.error("Demo failed: %s", e)
        raise
