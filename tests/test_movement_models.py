"""
test_movement_models.py — Tests for movement engine, adapters, and randomness utils.

Run: python -m pytest tests/test_movement_models.py -v
"""

import sys
import math
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.randomness import (
    gaussian_delay,
    weibull_delay,
    poisson_event_count,
    uniform_jitter,
    log_normal_delay,
    jitter_position,
    jitter_position_gaussian,
    chance,
    weighted_choice,
)
from utils.config_loader import ConfigLoader, reset_config


# ---------------------------------------------------------------------------
# Randomness utilities
# ---------------------------------------------------------------------------

class TestGaussianDelay(unittest.TestCase):
    """Tests for gaussian_delay()."""

    def test_returns_positive_when_min_zero(self):
        # Arrange + Act
        result = gaussian_delay(0.1, 0.02, min_val=0.0)
        # Assert
        self.assertGreaterEqual(result, 0.0)

    def test_clamped_to_min(self):
        # Arrange: std=0 forces result = mean
        result = gaussian_delay(0.0, 0.0, min_val=0.05)
        self.assertGreaterEqual(result, 0.05)

    def test_clamped_to_max(self):
        result = gaussian_delay(100.0, 0.0, max_val=1.0)
        self.assertLessEqual(result, 1.0)

    def test_distribution_mean_approx(self):
        # Arrange: large sample; mean should converge to target
        samples = [gaussian_delay(0.5, 0.1) for _ in range(1000)]
        mean = sum(samples) / len(samples)
        self.assertAlmostEqual(mean, 0.5, delta=0.05)


class TestWeibullDelay(unittest.TestCase):
    def test_always_positive(self):
        for _ in range(100):
            self.assertGreater(weibull_delay(0.2), 0)

    def test_scale_affects_magnitude(self):
        small_scale = [weibull_delay(0.1) for _ in range(200)]
        large_scale = [weibull_delay(1.0) for _ in range(200)]
        self.assertLess(
            sum(small_scale) / len(small_scale),
            sum(large_scale) / len(large_scale),
        )


class TestPoissonCount(unittest.TestCase):
    def test_non_negative(self):
        for _ in range(100):
            self.assertGreaterEqual(poisson_event_count(2.0), 0)

    def test_mean_approx(self):
        lam = 3.0
        samples = [poisson_event_count(lam) for _ in range(2000)]
        mean = sum(samples) / len(samples)
        self.assertAlmostEqual(mean, lam, delta=0.3)


class TestJitterPosition(unittest.TestCase):
    def test_within_radius(self):
        for _ in range(200):
            jx, jy = jitter_position(100, 100, radius=10)
            dist = math.hypot(jx - 100, jy - 100)
            self.assertLessEqual(dist, 10.5)  # slight float tolerance

    def test_gaussian_jitter_centered(self):
        xs, ys = [], []
        for _ in range(500):
            jx, jy = jitter_position_gaussian(0, 0, std=5.0)
            xs.append(jx)
            ys.append(jy)
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        self.assertAlmostEqual(mean_x, 0, delta=1.0)
        self.assertAlmostEqual(mean_y, 0, delta=1.0)


class TestChance(unittest.TestCase):
    def test_always_true_at_one(self):
        for _ in range(100):
            self.assertTrue(chance(1.0))

    def test_always_false_at_zero(self):
        for _ in range(100):
            self.assertFalse(chance(0.0))

    def test_probability_approx(self):
        count = sum(1 for _ in range(10000) if chance(0.3))
        self.assertAlmostEqual(count / 10000, 0.3, delta=0.03)


class TestWeightedChoice(unittest.TestCase):
    def test_selects_only_from_options(self):
        options = ["a", "b", "c"]
        for _ in range(50):
            result = weighted_choice(options, [1, 1, 1])
            self.assertIn(result, options)

    def test_heavily_weighted_item_dominates(self):
        options = ["rare", "common"]
        counts = {"rare": 0, "common": 0}
        for _ in range(1000):
            counts[weighted_choice(options, [1, 99])] += 1
        self.assertGreater(counts["common"], counts["rare"] * 5)


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

class TestConfigLoader(unittest.TestCase):
    def setUp(self):
        reset_config()

    def tearDown(self):
        reset_config()

    def test_defaults_loaded(self):
        cfg = ConfigLoader()
        self.assertEqual(cfg.get("movement.adapter"), "all")
        self.assertIsInstance(cfg.get("movement.fallback_chain"), list)

    def test_dot_notation_get(self):
        cfg = ConfigLoader()
        confidence = cfg.get("vision.match_confidence")
        self.assertIsInstance(confidence, float)
        self.assertGreater(confidence, 0)
        self.assertLessEqual(confidence, 1.0)

    def test_set_overrides_value(self):
        cfg = ConfigLoader()
        cfg.set("movement.adapter", "pyclick")
        self.assertEqual(cfg.get("movement.adapter"), "pyclick")

    def test_missing_key_returns_default(self):
        cfg = ConfigLoader()
        result = cfg.get("nonexistent.key", "fallback_value")
        self.assertEqual(result, "fallback_value")

    def test_deep_merge(self):
        cfg = ConfigLoader()
        # Override a nested key without losing siblings
        cfg.set("movement.overshoot_factor", 0.05)
        self.assertEqual(cfg.get("movement.overshoot_factor"), 0.05)
        # Sibling key should still be intact
        self.assertIsNotNone(cfg.get("movement.landing_jitter_std"))

    def test_invalid_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            ConfigLoader("/nonexistent/path/config.yaml")


# ---------------------------------------------------------------------------
# Movement engine (mocked adapters)
# ---------------------------------------------------------------------------

class TestMovementEngine(unittest.TestCase):
    """Tests for MovementEngine adapter resolution and move() logic."""

    def _make_mock_adapter(self, name: str, available: bool = True):
        adapter = MagicMock()
        adapter.name = name
        adapter.is_available.return_value = available
        adapter.move_to = MagicMock()
        return adapter

    @patch("core.movement_engine.MovementEngine._build_adapter_chain")
    def test_move_calls_adapter(self, mock_build):
        # Arrange
        from core.movement_engine import MovementEngine
        engine = MovementEngine.__new__(MovementEngine)
        engine._cfg = ConfigLoader()
        engine._timing = MagicMock()
        engine._timing.micro_pause_probability = 0.0  # disable micro pauses
        mock_adapter = self._make_mock_adapter("human_mouse")
        engine._adapter_chain = [mock_adapter]

        # Act
        with patch("utils.randomness.chance", return_value=False):
            engine.move(100, 200, apply_jitter=False)

        # Assert
        mock_adapter.move_to.assert_called_once()
        call_args = mock_adapter.move_to.call_args
        self.assertEqual(call_args[0][0], 100.0)
        self.assertEqual(call_args[0][1], 200.0)

    @patch("core.movement_engine.MovementEngine._build_adapter_chain")
    def test_no_adapters_raises(self, mock_build):
        from core.movement_engine import MovementEngine
        engine = MovementEngine.__new__(MovementEngine)
        engine._cfg = ConfigLoader()
        engine._timing = MagicMock()
        engine._adapter_chain = []
        with self.assertRaises(RuntimeError):
            engine.move(100, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
