"""
typing_engine.py — Human-like keyboard typing simulation.

Implements variable keystroke timing, burst typing patterns, realistic
hesitation, and optional typo injection with natural correction behavior.
All timing parameters are driven by TypingTimingProfile from timing_models.
"""

from __future__ import annotations

import logging
import random
import time
from typing import List, Optional

from utils.config_loader import get_config
from utils.timing_models import (
    TypingTimingProfile,
    TYPING_FAST, TYPING_NORMAL, TYPING_SLOW,
    sleep_keystroke,
)
from utils.randomness import chance, gaussian_delay, poisson_event_count

logger = logging.getLogger(__name__)

# Characters that commonly cause nearby-key typos (QWERTY layout proximity)
_QWERTY_NEIGHBORS: dict[str, list[str]] = {
    "a": ["s", "q", "w", "z"],
    "b": ["v", "g", "h", "n"],
    "c": ["x", "d", "f", "v"],
    "d": ["s", "e", "r", "f", "c", "x"],
    "e": ["w", "r", "d", "s"],
    "f": ["d", "r", "t", "g", "v", "c"],
    "g": ["f", "t", "y", "h", "b", "v"],
    "h": ["g", "y", "u", "j", "n", "b"],
    "i": ["u", "o", "k", "j"],
    "j": ["h", "u", "i", "k", "m", "n"],
    "k": ["j", "i", "o", "l", "m"],
    "l": ["k", "o", "p"],
    "m": ["n", "j", "k"],
    "n": ["b", "h", "j", "m"],
    "o": ["i", "p", "l", "k"],
    "p": ["o", "l"],
    "q": ["w", "a"],
    "r": ["e", "t", "f", "d"],
    "s": ["a", "w", "e", "d", "x", "z"],
    "t": ["r", "y", "g", "f"],
    "u": ["y", "i", "j", "h"],
    "v": ["c", "f", "g", "b"],
    "w": ["q", "e", "s", "a"],
    "x": ["z", "s", "d", "c"],
    "y": ["t", "u", "h", "g"],
    "z": ["a", "s", "x"],
}

_TYPING_PROFILES = {
    "fast": TYPING_FAST,
    "normal": TYPING_NORMAL,
    "slow": TYPING_SLOW,
}


class TypingEngine:
    """
    Simulates human-like keyboard typing.

    Features:
      - Gaussian inter-keystroke intervals
      - Random fast-typing burst sequences
      - Mid-word hesitation pauses
      - Typo injection with QWERTY-aware character substitution
      - Realistic backspace correction after typos
      - Clipboard paste for long strings (configurable threshold)

    Example:
        typer = TypingEngine()
        typer.type("Hello, my name is John.")
        typer.type("This is a longer paragraph...", profile_name="slow")
    """

    def __init__(
        self,
        input_controller=None,
        config_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            input_controller: Optional InputController for executing keystrokes.
                              Creates a new one if not provided.
            config_path: Optional config file path.
        """
        self._cfg = get_config(config_path)
        # Lazy import to avoid circular import at module level
        self._controller = input_controller
        self._profile: TypingTimingProfile = self._load_profile()
        self._enable_typos: bool = self._cfg.get("typing.enable_typos", True)
        self._paste_threshold: int = self._cfg.get("typing.paste_threshold", 80)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def type(
        self,
        text: str,
        profile_name: Optional[str] = None,
    ) -> None:
        """
        Type the given text with human-like timing and optional typos.

        Automatically chooses between keystroke simulation and clipboard paste
        based on text length and config threshold.

        Args:
            text: String to type.
            profile_name: Override timing profile ("fast" | "normal" | "slow").
        """
        profile = _TYPING_PROFILES.get(profile_name or "", self._profile)

        if len(text) > self._paste_threshold:
            logger.debug("Text length %d exceeds paste threshold; using clipboard.", len(text))
            self._paste(text)
            return

        self._type_with_timing(text, profile)

    def type_word_by_word(self, text: str, word_pause_mean: float = 0.08) -> None:
        """
        Type text word-by-word with a short pause between words.

        Slightly more realistic for longer sentences as humans often think
        word-by-word.

        Args:
            text: String to type.
            word_pause_mean: Mean pause between words in seconds.
        """
        words = text.split(" ")
        for i, word in enumerate(words):
            self._type_with_timing(word, self._profile)
            if i < len(words) - 1:
                # Type the space with a brief word-boundary pause
                time.sleep(gaussian_delay(word_pause_mean, 0.03, min_val=0.02))
                self._send_key(" ")

    def type_with_hesitation(self, text: str, hesitation_positions: List[int]) -> None:
        """
        Type text with hesitation pauses at specified character positions.

        Args:
            text: String to type.
            hesitation_positions: List of 0-based character indices to pause at.
        """
        for i, char in enumerate(text):
            if i in hesitation_positions:
                pause = gaussian_delay(0.5, 0.2, min_val=0.2)
                logger.debug("Hesitation pause at position %d: %.2fs", i, pause)
                time.sleep(pause)
            self._type_char(char, self._profile, in_burst=False)

    # ------------------------------------------------------------------
    # Internal typing logic
    # ------------------------------------------------------------------

    def _type_with_timing(self, text: str, profile: TypingTimingProfile) -> None:
        """Type text character-by-character with full timing model."""
        burst_remaining = 0

        for i, char in enumerate(text):
            in_burst = burst_remaining > 0

            # Decide if starting a new burst
            if not in_burst and chance(profile.burst_probability):
                burst_remaining = max(1, int(random.gauss(profile.burst_length_mean, 2.0)))
                in_burst = True
                logger.debug("Burst started: %d chars", burst_remaining)

            # Hesitation check (not in burst)
            if not in_burst and chance(profile.hesitation_probability):
                pause = gaussian_delay(
                    profile.hesitation_duration_mean,
                    profile.hesitation_duration_std,
                    min_val=0.1,
                )
                logger.debug("Typing hesitation: %.2fs", pause)
                time.sleep(pause)

            # Typo injection
            if self._enable_typos and char.isalpha() and chance(profile.typo_probability):
                self._inject_typo_and_correct(char, profile)
            else:
                self._type_char(char, profile, in_burst=in_burst)

            if burst_remaining > 0:
                burst_remaining -= 1

    def _type_char(
        self,
        char: str,
        profile: TypingTimingProfile,
        in_burst: bool = False,
    ) -> None:
        """Type a single character with appropriate timing."""
        self._send_key(char)
        sleep_keystroke(profile, in_burst=in_burst)

    def _inject_typo_and_correct(self, intended: str, profile: TypingTimingProfile) -> None:
        """
        Type a nearby-key typo, pause to "notice" it, then backspace and retype.

        Args:
            intended: The character that was intended.
            profile: Typing timing profile.
        """
        typo_char = self._get_typo_char(intended)
        logger.debug("Typo: '%s' instead of '%s'", typo_char, intended)

        self._send_key(typo_char)
        sleep_keystroke(profile, in_burst=False)

        # Optionally type 1–2 more chars before noticing (realistic)
        chars_before_notice = random.randint(0, 2)
        for _ in range(chars_before_notice):
            self._send_key(random.choice("abcdefghijklmnopqrstuvwxyz"))
            sleep_keystroke(profile, in_burst=False)

        # "Notice" the typo — brief pause
        notice_delay = gaussian_delay(profile.correction_delay_mean, 0.1, min_val=0.1)
        time.sleep(notice_delay)

        # Backspace to correct
        backspace_count = 1 + chars_before_notice
        for _ in range(backspace_count):
            self._send_key("backspace")
            time.sleep(gaussian_delay(0.08, 0.03, min_val=0.04))

        # Type the intended character
        self._send_key(intended)
        sleep_keystroke(profile, in_burst=False)

    def _get_typo_char(self, char: str) -> str:
        """Return a nearby-key typo for the given character."""
        lower = char.lower()
        neighbors = _QWERTY_NEIGHBORS.get(lower, [])
        if not neighbors:
            # No known neighbors; repeat char or use adjacent key
            return char
        typo = random.choice(neighbors)
        # Preserve original case
        return typo.upper() if char.isupper() else typo

    def _send_key(self, key: str) -> None:
        """Send a single keystroke via the controller or pyautogui directly."""
        if self._controller is None:
            from core.input_controller import InputController
            self._controller = InputController()
        try:
            import pyautogui  # type: ignore[import]
            if len(key) == 1:
                pyautogui.typewrite(key, interval=0)
            else:
                pyautogui.press(key)
        except ImportError:
            logger.error("PyAutoGUI not installed; cannot send keystroke.")

    def _paste(self, text: str) -> None:
        """Paste text via clipboard."""
        if self._controller:
            self._controller.paste_text(text)
        else:
            try:
                import pyperclip  # type: ignore[import]
                import pyautogui  # type: ignore[import]
                pyperclip.copy(text)
                pyautogui.hotkey("ctrl", "v")
            except ImportError:
                logger.warning("pyperclip not installed; large text paste unavailable.")

    def _load_profile(self) -> TypingTimingProfile:
        profile_name = self._cfg.get("behavior.typing_profile", "normal")
        return _TYPING_PROFILES.get(profile_name, TYPING_NORMAL)
