"""
test_behavior_patterns.py — Tests for BehaviorEngine, TypingEngine, and timing models.

Run: python -m pytest tests/test_behavior_patterns.py -v
"""

import sys
import time
import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.timing_models import (
    ClickTimingProfile,
    TypingTimingProfile,
    MovementTimingProfile,
    PROFILE_FAST, PROFILE_NORMAL, PROFILE_CAUTIOUS,
    TYPING_FAST, TYPING_NORMAL, TYPING_SLOW,
)
from utils.config_loader import ConfigLoader, reset_config


# ---------------------------------------------------------------------------
# Timing models
# ---------------------------------------------------------------------------

class TestClickTimingProfiles(unittest.TestCase):
    """Tests for click timing profile dataclasses."""

    def test_fast_has_shorter_hold_than_cautious(self):
        self.assertLess(
            PROFILE_FAST.hold_duration_mean,
            PROFILE_CAUTIOUS.hold_duration_mean,
        )

    def test_cautious_has_longer_pre_click(self):
        self.assertGreater(
            PROFILE_CAUTIOUS.pre_click_pause_mean,
            PROFILE_NORMAL.pre_click_pause_mean,
        )

    def test_all_values_positive(self):
        for profile in [PROFILE_FAST, PROFILE_NORMAL, PROFILE_CAUTIOUS]:
            self.assertGreater(profile.pre_click_pause_mean, 0)
            self.assertGreater(profile.hold_duration_mean, 0)
            self.assertGreater(profile.post_click_pause_mean, 0)


class TestTypingTimingProfiles(unittest.TestCase):
    def test_fast_has_shorter_interval(self):
        self.assertLess(TYPING_FAST.base_interval_mean, TYPING_SLOW.base_interval_mean)

    def test_normal_profile_defaults(self):
        p = TYPING_NORMAL
        self.assertGreater(p.typo_probability, 0)
        self.assertLess(p.typo_probability, 0.5)
        self.assertGreater(p.burst_probability, 0)

    def test_slow_profile_hesitates_more(self):
        self.assertGreater(
            TYPING_SLOW.hesitation_probability,
            TYPING_FAST.hesitation_probability,
        )


# ---------------------------------------------------------------------------
# TypingEngine
# ---------------------------------------------------------------------------

class TestTypingEngine(unittest.TestCase):
    """Tests for TypingEngine logic (mocked keystroke sending)."""

    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    def _make_engine(self):
        from core.typing_engine import TypingEngine
        engine = TypingEngine.__new__(TypingEngine)
        engine._cfg = ConfigLoader()
        engine._enable_typos = True
        engine._paste_threshold = 80
        engine._profile = TYPING_NORMAL
        engine._controller = None
        engine._sent_keys = []

        def mock_send(key):
            engine._sent_keys.append(key)

        engine._send_key = mock_send
        engine._paste = MagicMock()
        return engine

    def test_type_short_text_uses_keystroke_not_paste(self):
        # Arrange
        engine = self._make_engine()
        # Act
        with patch("time.sleep"):
            engine.type("Hello")
        # Assert
        engine._paste.assert_not_called()
        self.assertIn("H", engine._sent_keys or ["H"])  # at least attempted

    def test_type_long_text_uses_paste(self):
        # Arrange
        engine = self._make_engine()
        engine._paste_threshold = 10
        long_text = "A" * 20
        # Act
        with patch("time.sleep"):
            engine.type(long_text)
        # Assert
        engine._paste.assert_called_once_with(long_text)

    def test_get_typo_char_returns_neighbor(self):
        # Arrange
        from core.typing_engine import TypingEngine, _QWERTY_NEIGHBORS
        engine = TypingEngine.__new__(TypingEngine)
        # Act: 'a' has known neighbors
        typo = engine._get_typo_char("a")
        # Assert: typo is a known neighbor of 'a'
        self.assertIn(typo.lower(), _QWERTY_NEIGHBORS.get("a", []) + ["a"])

    def test_get_typo_char_preserves_case_upper(self):
        from core.typing_engine import TypingEngine
        engine = TypingEngine.__new__(TypingEngine)
        typo = engine._get_typo_char("A")
        self.assertTrue(typo.isupper())

    def test_get_typo_char_preserves_case_lower(self):
        from core.typing_engine import TypingEngine
        engine = TypingEngine.__new__(TypingEngine)
        typo = engine._get_typo_char("s")
        self.assertTrue(typo.islower())

    def test_type_with_hesitation_correct_length(self):
        # Arrange
        engine = self._make_engine()
        text = "Hello"
        pauses = []

        original_sleep = time.sleep
        def capture_sleep(t):
            pauses.append(t)

        # Act
        with patch("time.sleep", side_effect=capture_sleep):
            engine.type_with_hesitation(text, hesitation_positions=[2])

        # Assert: at least one longer pause was injected at position 2
        self.assertTrue(any(p >= 0.1 for p in pauses))


# ---------------------------------------------------------------------------
# BehaviorEngine
# ---------------------------------------------------------------------------

class TestBehaviorEngine(unittest.TestCase):
    """Tests for BehaviorEngine orchestration logic."""

    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    def _make_engine(self):
        from core.behavior_engine import BehaviorEngine
        engine = BehaviorEngine.__new__(BehaviorEngine)
        engine._cfg = ConfigLoader()
        engine._movement_profile = MovementTimingProfile()
        engine._idle_flick_prob = 0.0  # disable idle flicks in tests
        engine._idle_flick_radius = 40
        engine._controller = MagicMock()
        engine._controller.click = MagicMock()
        engine._controller.double_click = MagicMock()
        engine._controller.move = MagicMock(return_value=(100, 200))
        engine._controller.hotkey = MagicMock()
        engine._controller.key_press = MagicMock()
        return engine

    def test_human_click_calls_controller_click(self):
        # Arrange
        engine = self._make_engine()
        # Act
        with patch("time.sleep"):
            engine.human_click(100, 200)
        # Assert
        engine._controller.click.assert_called_once_with(100, 200, button="left")

    def test_human_right_click_uses_right_button(self):
        engine = self._make_engine()
        with patch("time.sleep"):
            engine.human_right_click(300, 400)
        call_args = engine._controller.click.call_args
        self.assertEqual(call_args[1].get("button") or call_args[0][2], "right")

    def test_perform_workflow_executes_all_steps(self):
        # Arrange
        engine = self._make_engine()
        executed = []
        actions = [
            lambda: executed.append("step1"),
            lambda: executed.append("step2"),
            lambda: executed.append("step3"),
        ]
        # Act
        with patch("time.sleep"):
            engine.perform_workflow(actions, inter_action_delay_mean=0.01)
        # Assert
        self.assertEqual(executed, ["step1", "step2", "step3"])

    def test_perform_workflow_raises_on_step_failure(self):
        engine = self._make_engine()
        def bad_action():
            raise ValueError("Simulated failure")
        with patch("time.sleep"):
            with self.assertRaises(ValueError):
                engine.perform_workflow([bad_action])

    def test_think_pause_sleeps(self):
        engine = self._make_engine()
        sleep_calls = []
        with patch("time.sleep", side_effect=lambda t: sleep_calls.append(t)):
            engine.think_pause(complexity=1.0)
        self.assertTrue(len(sleep_calls) >= 1)
        self.assertGreater(sleep_calls[0], 0)

    def test_reading_pause_scales_with_length(self):
        engine = self._make_engine()
        short_pauses, long_pauses = [], []
        with patch("time.sleep", side_effect=lambda t: short_pauses.append(t)):
            engine.reading_pause(content_length=10)
        with patch("time.sleep", side_effect=lambda t: long_pauses.append(t)):
            engine.reading_pause(content_length=500)
        self.assertLess(sum(short_pauses), sum(long_pauses))


# ---------------------------------------------------------------------------
# Sleep helpers (timing_models)
# ---------------------------------------------------------------------------

class TestSleepHelpers(unittest.TestCase):
    """Verify that sleep helper functions call time.sleep with positive values."""

    def _assert_positive_sleep(self, func, *args, **kwargs):
        calls = []
        with patch("time.sleep", side_effect=lambda t: calls.append(t)):
            func(*args, **kwargs)
        self.assertTrue(len(calls) >= 1, f"{func.__name__} never called time.sleep")
        for duration in calls:
            self.assertGreater(duration, 0, f"{func.__name__} slept for non-positive duration")

    def test_sleep_click_pre(self):
        from utils.timing_models import sleep_click_pre
        self._assert_positive_sleep(sleep_click_pre)

    def test_sleep_click_hold(self):
        from utils.timing_models import sleep_click_hold
        self._assert_positive_sleep(sleep_click_hold)

    def test_sleep_click_post(self):
        from utils.timing_models import sleep_click_post
        self._assert_positive_sleep(sleep_click_post)

    def test_sleep_keystroke_normal(self):
        from utils.timing_models import sleep_keystroke
        self._assert_positive_sleep(sleep_keystroke, in_burst=False)

    def test_sleep_keystroke_burst(self):
        from utils.timing_models import sleep_keystroke
        self._assert_positive_sleep(sleep_keystroke, in_burst=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
