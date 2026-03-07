"""
config_loader.py — Configuration loading and validation for the framework.

Supports YAML and JSON config files with sensible defaults. Config is loaded
once and cached; individual modules pull their sections via get().
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

# Optional YAML support (falls back to JSON-only if PyYAML not installed)
try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "movement": {
        # Primary adapter: "human_mouse" | "pyclick" | "humancursor" | "all"
        "adapter": "all",
        # Ordered fallback chain when adapter = "all" or primary fails
        "fallback_chain": ["human_mouse", "pyclick", "humancursor"],
        # Pixels of overshoot before correcting onto target
        "overshoot_factor": 0.03,
        # Minimum movement duration in seconds
        "min_move_duration": 0.3,
        # Maximum movement duration in seconds
        "max_move_duration": 3.0,
        # Gaussian jitter std dev applied to landing position (pixels)
        "landing_jitter_std": 2.5,
    },
    "behavior": {
        # Click timing profile: "fast" | "normal" | "cautious"
        "click_profile": "normal",
        # Typing timing profile: "fast" | "normal" | "slow"
        "typing_profile": "normal",
        # Probability of idle micro-flick between actions [0.0–1.0]
        "idle_flick_probability": 0.03,
        # Max idle flick radius in pixels
        "idle_flick_radius": 40,
    },
    "typing": {
        # Enable typo simulation
        "enable_typos": True,
        # Global typo probability override (null = use profile default)
        "typo_probability": None,
        # Clipboard paste threshold: strings longer than this are pasted
        "paste_threshold": 80,
    },
    "vision": {
        # Default template matching confidence threshold [0.0–1.0]
        "match_confidence": 0.85,
        # Screenshot region: null = full screen, or [x, y, w, h]
        "capture_region": None,
        # Grayscale matching (faster, slightly less accurate)
        "grayscale_matching": True,
    },
    "logging": {
        # Log level: "DEBUG" | "INFO" | "WARNING" | "ERROR"
        "level": "INFO",
        # Log to file path (null = console only)
        "file": None,
    },
}


# ---------------------------------------------------------------------------
# Config manager
# ---------------------------------------------------------------------------

class ConfigLoader:
    """
    Loads, merges, and exposes framework configuration.

    Usage:
        config = ConfigLoader("path/to/config.yaml")
        adapter = config.get("movement.adapter")
    """

    def __init__(self, path: Optional[str] = None) -> None:
        """
        Initialize with an optional path to a YAML or JSON config file.

        Args:
            path: Absolute or relative path to config file. If None, searches
                  for `automation_config.yaml` / `automation_config.json` in
                  the current working directory, then uses defaults.
        """
        self._config: Dict[str, Any] = self._deep_copy(_DEFAULTS)
        self._explicit_path = path is not None

        resolved = self._resolve_path(path)
        if resolved:
            user_config = self._load_file(resolved)
            self._deep_merge(self._config, user_config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Retrieve a config value using dot-notation key path.

        Args:
            key_path: Dot-separated path, e.g. "movement.adapter".
            default: Value to return if key not found.

        Returns:
            Config value or default.
        """
        parts = key_path.split(".")
        node = self._config
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key_path: str, value: Any) -> None:
        """
        Override a config value at runtime.

        Args:
            key_path: Dot-separated path to the key.
            value: New value to assign.
        """
        parts = key_path.split(".")
        node = self._config
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def as_dict(self) -> Dict[str, Any]:
        """Return a shallow copy of the full config dict."""
        return dict(self._config)

    def movement_adapter(self) -> str:
        """Convenience: return the configured movement adapter name."""
        return self.get("movement.adapter", "all")

    def fallback_chain(self) -> list:
        """Convenience: return the adapter fallback chain."""
        return self.get("movement.fallback_chain", ["human_mouse", "pyclick", "humancursor"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_path(self, path: Optional[str]) -> Optional[Path]:
        if path:
            p = Path(path)
            if p.exists():
                return p
            raise FileNotFoundError(f"Config file not found: {path}")
        # Auto-discover
        for candidate in ("automation_config.yaml", "automation_config.json"):
            p = Path.cwd() / candidate
            if p.exists():
                return p
        return None

    def _load_file(self, path: Path) -> Dict[str, Any]:
        suffix = path.suffix.lower()
        with open(path, "r", encoding="utf-8") as fh:
            if suffix in (".yaml", ".yml"):
                if not _YAML_AVAILABLE:
                    if self._explicit_path:
                        raise ImportError(
                            "PyYAML is required to load YAML config files. "
                            "Install: pip install pyyaml"
                        )
                    # Auto-discovered YAML without PyYAML — warn and use defaults
                    import logging as _log
                    _log.getLogger(__name__).warning(
                        "Found %s but PyYAML is not installed. "
                        "Using defaults. Install pyyaml to load this file.",
                        path,
                    )
                    return {}
                return yaml.safe_load(fh) or {}
            elif suffix == ".json":
                return json.load(fh)
        raise ValueError(f"Unsupported config file format: {suffix}")

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        """Recursively merge override into base (modifies base in-place)."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                ConfigLoader._deep_merge(base[key], value)
            else:
                base[key] = value

    @staticmethod
    def _deep_copy(d: dict) -> dict:
        """Simple recursive deep copy for plain dicts."""
        result = {}
        for k, v in d.items():
            result[k] = ConfigLoader._deep_copy(v) if isinstance(v, dict) else v
        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[ConfigLoader] = None


def get_config(path: Optional[str] = None) -> ConfigLoader:
    """
    Return the module-level singleton ConfigLoader.

    Args:
        path: Config file path. Only used on first call; subsequent calls
              return the cached instance.

    Returns:
        ConfigLoader instance.
    """
    global _instance
    if _instance is None:
        _instance = ConfigLoader(path)
    return _instance


def reset_config() -> None:
    """Reset the singleton (useful in tests)."""
    global _instance
    _instance = None
