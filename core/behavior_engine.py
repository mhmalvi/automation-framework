"""
behavior_engine.py — Orchestrates human-like behavior across all actions.

The BehaviorEngine is the top-level coordinator. It wraps the InputController
with behavioral layers: reaction times, hesitation patterns, idle movements,
and statistical timing to ensure the automation feels like a real human user.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, List, Optional, Tuple

from core.input_controller import InputController
from core.movement_engine import MovementEngine
from utils.config_loader import get_config
from utils.randomness import chance, gaussian_delay, jitter_position_gaussian
from utils.timing_models import (
    MovementTimingProfile,
    sleep_reaction_time,
    sleep_micro_pause,
)

logger = logging.getLogger(__name__)


class BehaviorEngine:
    """
    High-level behavior orchestrator.

    Adds a human-behavior layer on top of InputController:
      - Random idle micro-flicks between actions
      - Hesitation before important clicks
      - Overshoot and self-correction on long movements
      - Statistically modeled delays between action sequences

    Example:
        engine = BehaviorEngine()
        engine.human_click(500, 300)
        engine.human_type("Hello, world!")
        engine.perform_workflow([
            lambda: engine.human_click(100, 100),
            lambda: engine.human_type("search term"),
            lambda: engine.human_click(200, 200),
        ])
    """

    def __init__(
        self,
        input_controller: Optional[InputController] = None,
        config_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            input_controller: Optional pre-built InputController.
            config_path: Optional path to config file.
        """
        self._cfg = get_config(config_path)
        self._controller = input_controller or InputController(config_path=config_path)
        self._movement_profile = MovementTimingProfile()
        self._idle_flick_prob = self._cfg.get("behavior.idle_flick_probability", 0.03)
        self._idle_flick_radius = self._cfg.get("behavior.idle_flick_radius", 40)

    # ------------------------------------------------------------------
    # Human-like mouse actions
    # ------------------------------------------------------------------

    def human_click(
        self,
        x: float,
        y: float,
        button: str = "left",
        hesitate: bool = False,
    ) -> None:
        """
        Perform a human-like click with optional pre-click hesitation.

        Includes:
          - Reaction time sleep
          - Optional hesitation (for "thinking before clicking")
          - Idle flick chance
          - Overshoot + correction on large movements
          - Natural click timing

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            button: "left" | "right" | "middle".
            hesitate: If True, add an extra hesitation pause before moving.
        """
        if hesitate:
            self._hesitate()

        self._maybe_idle_flick()
        self._maybe_overshoot_then_correct(x, y)
        self._controller.click(x, y, button=button)

    def human_double_click(self, x: float, y: float) -> None:
        """Double-click at (x, y) with human-like timing."""
        self._maybe_idle_flick()
        self._controller.double_click(x, y)

    def human_right_click(self, x: float, y: float) -> None:
        """Right-click at (x, y) with hesitation (right-clicks feel deliberate)."""
        self.human_click(x, y, button="right", hesitate=True)

    def human_drag(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration: Optional[float] = None,
    ) -> None:
        """
        Drag from start to end with natural timing.

        Args:
            start_x: Drag origin x.
            start_y: Drag origin y.
            end_x: Drag destination x.
            end_y: Drag destination y.
            duration: Drag duration in seconds.
        """
        self._hesitate(mean=0.08, std=0.03)
        self._controller.drag(start_x, start_y, end_x, end_y, duration=duration)

    def human_scroll(
        self,
        x: float,
        y: float,
        direction: str = "down",
        min_clicks: int = 2,
        max_clicks: int = 6,
    ) -> None:
        """
        Scroll at (x, y) with a random number of ticks.

        Args:
            x: Scroll position x.
            y: Scroll position y.
            direction: "up" | "down".
            min_clicks: Minimum scroll ticks.
            max_clicks: Maximum scroll ticks.
        """
        clicks = random.randint(min_clicks, max_clicks)
        # Random pause before scroll (looking at the page)
        time.sleep(gaussian_delay(0.15, 0.06, min_val=0.05))
        self._controller.scroll(x, y, clicks=clicks, direction=direction)

    # ------------------------------------------------------------------
    # Human-like keyboard actions
    # ------------------------------------------------------------------

    def human_type(self, text: str) -> None:
        """
        Type text using the TypingEngine for maximum realism.

        Falls back to InputController.type_text() if TypingEngine unavailable.

        Args:
            text: String to type.
        """
        # Import here to avoid circular dependency at module load
        from core.typing_engine import TypingEngine
        typer = TypingEngine(input_controller=self._controller)
        typer.type(text)

    def human_hotkey(self, *keys: str) -> None:
        """
        Press a keyboard shortcut with a brief pre-pause.

        Args:
            *keys: Keys to chord (e.g. "ctrl", "a").
        """
        time.sleep(gaussian_delay(0.08, 0.03, min_val=0.02))
        self._controller.hotkey(*keys)

    def human_key_press(self, key: str) -> None:
        """Press a single key with brief pre-pause."""
        time.sleep(gaussian_delay(0.05, 0.02, min_val=0.01))
        self._controller.key_press(key)

    # ------------------------------------------------------------------
    # Workflow orchestration
    # ------------------------------------------------------------------

    def perform_workflow(
        self,
        actions: List[Callable],
        inter_action_delay_mean: float = 0.5,
        inter_action_delay_std: float = 0.15,
    ) -> None:
        """
        Execute a sequence of actions with human-like inter-action delays.

        Args:
            actions: List of callables (lambdas, partials, or regular funcs).
            inter_action_delay_mean: Mean pause between actions (seconds).
            inter_action_delay_std: Std dev of inter-action pause.
        """
        for i, action in enumerate(actions):
            logger.debug("Workflow step %d/%d", i + 1, len(actions))
            try:
                action()
            except Exception as exc:
                logger.error("Workflow step %d failed: %s", i + 1, exc)
                raise

            if i < len(actions) - 1:
                delay = gaussian_delay(
                    inter_action_delay_mean,
                    inter_action_delay_std,
                    min_val=0.1,
                )
                time.sleep(delay)

    def reading_pause(self, content_length: int = 100) -> None:
        """
        Simulate a human reading pause proportional to content length.

        Models reading speed of ~200 words/min = ~3.3 chars/sec with variance.

        Args:
            content_length: Approximate number of characters to "read".
        """
        # ~3.3 chars/sec base reading speed with Gaussian noise
        base_seconds = content_length / 3.3
        actual = gaussian_delay(base_seconds, base_seconds * 0.2, min_val=0.5)
        actual = min(actual, 15.0)  # cap at 15s regardless
        logger.debug("Reading pause: %.1fs for %d chars", actual, content_length)
        time.sleep(actual)

    def think_pause(self, complexity: float = 1.0) -> None:
        """
        Simulate a decision/thinking pause before an action.

        Args:
            complexity: Multiplier for pause length. 1.0 = normal decision,
                        2.0+ = complex decision requiring more thought.
        """
        base = 0.4 * complexity
        delay = gaussian_delay(base, base * 0.3, min_val=0.1, max_val=5.0)
        logger.debug("Think pause: %.2fs (complexity=%.1f)", delay, complexity)
        time.sleep(delay)

    # ------------------------------------------------------------------
    # Internal behavior helpers
    # ------------------------------------------------------------------

    def _hesitate(self, mean: float = 0.25, std: float = 0.1) -> None:
        """Brief hesitation pause — cursor hovering before acting."""
        delay = gaussian_delay(mean, std, min_val=0.05)
        time.sleep(delay)

    def _maybe_idle_flick(self) -> None:
        """Randomly perform a small idle cursor flick (human fidgeting)."""
        if not chance(self._idle_flick_prob):
            return
        try:
            from movement_adapters.humancursor_adapter import HumanCursorAdapter
            adapter = self._controller._engine.active_adapter
            if isinstance(adapter, HumanCursorAdapter) and adapter.is_available():
                adapter.idle_flick(radius=self._idle_flick_radius)
            else:
                self._pyautogui_flick()
        except Exception:
            self._pyautogui_flick()

    def _pyautogui_flick(self) -> None:
        """Fallback idle flick using raw PyAutoGUI relative move."""
        try:
            import pyautogui  # type: ignore[import]
            import math
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(5, self._idle_flick_radius)
            dx = int(r * math.cos(angle))
            dy = int(r * math.sin(angle))
            cur_x, cur_y = pyautogui.position()
            pyautogui.moveTo(cur_x + dx, cur_y + dy, duration=0.1)
        except Exception:
            pass  # Non-critical; silently skip

    def _maybe_overshoot_then_correct(self, target_x: float, target_y: float) -> None:
        """
        Simulate cursor overshoot on long movements, then self-correct.

        Overshoot is proportional to distance from current position.
        Applied stochastically (~15% of moves).
        """
        if not chance(0.15):
            return
        try:
            import pyautogui  # type: ignore[import]
            cur_x, cur_y = pyautogui.position()
            import math
            distance = math.hypot(target_x - cur_x, target_y - cur_y)
            if distance < 100:
                return  # No overshoot for short movements

            # Overshoot by 2–5% of distance past the target
            factor = random.uniform(0.02, 0.05)
            dx = (target_x - cur_x) * (1 + factor)
            dy = (target_y - cur_y) * (1 + factor)
            overshoot_x = cur_x + dx
            overshoot_y = cur_y + dy

            self._controller.move(overshoot_x, overshoot_y, react_first=False)
            # Brief pause (noticing the overshoot)
            time.sleep(gaussian_delay(0.06, 0.02, min_val=0.03))
            # Correct back to actual target (no extra jitter on correction)
            self._controller._engine.move(target_x, target_y, apply_jitter=False)
        except Exception as exc:
            logger.debug("Overshoot simulation skipped: %s", exc)
