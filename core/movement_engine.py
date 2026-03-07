"""
movement_engine.py — Abstract interface and dispatcher for movement adapters.

All concrete movement adapters (human_mouse, pyclick, humancursor) implement
the BaseMovementAdapter interface. The MovementEngine selects the active
adapter based on config and provides a consistent API to the rest of the
framework.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from utils.config_loader import get_config
from utils.randomness import jitter_position_gaussian, chance
from utils.timing_models import MovementTimingProfile, sleep_micro_pause

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class BaseMovementAdapter(ABC):
    """
    Abstract contract that every movement adapter must satisfy.

    Each adapter wraps a third-party motion library and exposes a uniform
    interface so the MovementEngine and higher layers never depend on
    library-specific internals.
    """

    #: Human-readable name used in config and logging
    name: str = "base"

    @abstractmethod
    def move_to(
        self,
        x: float,
        y: float,
        duration: Optional[float] = None,
    ) -> None:
        """
        Move the cursor to absolute screen coordinates (x, y).

        Args:
            x: Target x coordinate in pixels.
            y: Target y coordinate in pixels.
            duration: Desired travel time in seconds. If None the adapter
                      decides based on distance.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """
        Return True if the underlying library is importable and functional.

        Used by MovementEngine to build the active fallback chain at runtime.
        """


# ---------------------------------------------------------------------------
# Movement engine
# ---------------------------------------------------------------------------

class MovementEngine:
    """
    Selects and invokes the appropriate movement adapter(s) based on config.

    Adapter selection modes (set via config "movement.adapter"):
        - "human_mouse"  — use only the human_mouse adapter
        - "pyclick"      — use only the PyClick adapter
        - "humancursor"  — use only the HumanCursor adapter
        - "all"          — try each adapter in fallback_chain order; use the
                           first available one. This is the default.

    Example:
        engine = MovementEngine()
        engine.move(800, 400)
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        """
        Initialize and resolve the active adapter from config.

        Args:
            config_path: Optional path to a config file. Uses global singleton
                         config if not provided.
        """
        self._cfg = get_config(config_path)
        self._timing = MovementTimingProfile()
        self._adapter: Optional[BaseMovementAdapter] = None
        self._adapter_chain: List[BaseMovementAdapter] = []
        self._build_adapter_chain()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def move(
        self,
        x: float,
        y: float,
        duration: Optional[float] = None,
        apply_jitter: bool = True,
    ) -> Tuple[float, float]:
        """
        Move the cursor to (x, y) using the configured adapter.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            duration: Travel duration in seconds (adapter may override).
            apply_jitter: Apply Gaussian landing jitter if True (default).

        Returns:
            (actual_x, actual_y) — coordinates the cursor landed on.

        Raises:
            RuntimeError: If no adapters are available.
        """
        if not self._adapter_chain:
            raise RuntimeError(
                "No movement adapters are available. "
                "Install at least one of: human-mouse, pyclick, humancursor"
            )

        # Apply landing jitter to simulate imprecise human targeting
        target_x, target_y = x, y
        if apply_jitter:
            std = self._cfg.get("movement.landing_jitter_std", 2.5)
            target_x, target_y = jitter_position_gaussian(x, y, std=std)

        # Micro-pause mid-move simulation
        if chance(self._timing.micro_pause_probability):
            sleep_micro_pause(self._timing)

        adapter = self._adapter_chain[0]
        logger.debug("Moving to (%.1f, %.1f) via adapter '%s'", target_x, target_y, adapter.name)
        adapter.move_to(target_x, target_y, duration=duration)

        return target_x, target_y

    def set_adapter(self, name: str) -> None:
        """
        Switch the active adapter at runtime.

        Args:
            name: Adapter name ("human_mouse", "pyclick", "humancursor", "all").

        Raises:
            ValueError: If name is unknown or adapter is unavailable.
        """
        self._cfg.set("movement.adapter", name)
        self._build_adapter_chain()
        if not self._adapter_chain:
            raise ValueError(f"Adapter '{name}' is not available in this environment.")
        logger.info("Active movement adapter set to: %s", self._adapter_chain[0].name)

    @property
    def active_adapter(self) -> Optional[BaseMovementAdapter]:
        """Return the first adapter in the active chain."""
        return self._adapter_chain[0] if self._adapter_chain else None

    @property
    def available_adapters(self) -> List[str]:
        """Return names of all adapters that are currently available."""
        return [a.name for a in self._adapter_chain]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_adapter_chain(self) -> None:
        """Resolve and validate adapters based on current config."""
        # Import here to avoid circular imports; adapters import this module's
        # BaseMovementAdapter which is already defined above.
        from movement_adapters.human_mouse_adapter import HumanMouseAdapter
        from movement_adapters.pyclick_adapter import PyClickAdapter
        from movement_adapters.humancursor_adapter import HumanCursorAdapter

        all_adapters: dict[str, BaseMovementAdapter] = {
            "human_mouse": HumanMouseAdapter(),
            "pyclick": PyClickAdapter(),
            "humancursor": HumanCursorAdapter(),
        }

        mode = self._cfg.get("movement.adapter", "all")
        chain_names: List[str]

        if mode == "all":
            chain_names = self._cfg.get(
                "movement.fallback_chain",
                ["human_mouse", "pyclick", "humancursor"],
            )
        elif mode in all_adapters:
            chain_names = [mode]
        else:
            raise ValueError(
                f"Unknown adapter mode '{mode}'. "
                f"Valid options: all, human_mouse, pyclick, humancursor"
            )

        self._adapter_chain = [
            all_adapters[name]
            for name in chain_names
            if name in all_adapters and all_adapters[name].is_available()
        ]

        if not self._adapter_chain:
            logger.warning(
                "None of the requested adapters (%s) are available. "
                "Movements will fail until a library is installed.",
                chain_names,
            )
        else:
            logger.debug(
                "Movement adapter chain resolved: %s",
                [a.name for a in self._adapter_chain],
            )
