"""
timing_models.py — Human timing profiles for various interaction types.

Encapsulates scientifically-informed delay models for mouse clicks, keyboard
input, hesitations, and idle micro-movements. All durations are in seconds.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from utils.randomness import gaussian_delay, weibull_delay, log_normal_delay


# ---------------------------------------------------------------------------
# Timing profile dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ClickTimingProfile:
    """
    Timing parameters for a mouse click interaction.

    Attributes:
        pre_click_pause_mean: Mean pause before pressing down (seconds).
        pre_click_pause_std: Std dev of pre-click pause.
        hold_duration_mean: Mean button-hold duration (seconds).
        hold_duration_std: Std dev of hold duration.
        post_click_pause_mean: Mean pause after releasing (seconds).
        post_click_pause_std: Std dev of post-click pause.
    """
    pre_click_pause_mean: float = 0.05
    pre_click_pause_std: float = 0.02
    hold_duration_mean: float = 0.08
    hold_duration_std: float = 0.03
    post_click_pause_mean: float = 0.06
    post_click_pause_std: float = 0.025


@dataclass
class TypingTimingProfile:
    """
    Timing parameters for keyboard typing behavior.

    Attributes:
        base_interval_mean: Mean inter-keystroke interval (seconds).
        base_interval_std: Std dev of interval.
        burst_probability: Probability of entering a fast-typing burst.
        burst_interval_mean: Mean interval during a burst.
        burst_interval_std: Std dev during a burst.
        burst_length_mean: Mean number of characters in a burst.
        hesitation_probability: Probability of pausing mid-word.
        hesitation_duration_mean: Mean hesitation duration (seconds).
        hesitation_duration_std: Std dev of hesitation.
        typo_probability: Probability of a typo on any given keystroke.
        correction_delay_mean: Mean time before correcting a typo (seconds).
    """
    base_interval_mean: float = 0.12
    base_interval_std: float = 0.04
    burst_probability: float = 0.15
    burst_interval_mean: float = 0.06
    burst_interval_std: float = 0.02
    burst_length_mean: float = 5.0
    hesitation_probability: float = 0.05
    hesitation_duration_mean: float = 0.4
    hesitation_duration_std: float = 0.15
    typo_probability: float = 0.02
    correction_delay_mean: float = 0.3


@dataclass
class MovementTimingProfile:
    """
    Timing parameters for mouse movement behavior.

    Attributes:
        reaction_time_scale: Weibull scale for reaction time before moving.
        reaction_time_shape: Weibull shape for reaction time (1.5 = human RT).
        overshoot_correction_delay_mean: Pause after overshoot before correcting.
        micro_pause_probability: Probability of a micro-pause mid-trajectory.
        micro_pause_duration_mean: Mean micro-pause duration (seconds).
        idle_flick_probability: Probability of a random idle movement.
    """
    reaction_time_scale: float = 0.15
    reaction_time_shape: float = 1.5
    overshoot_correction_delay_mean: float = 0.06
    micro_pause_probability: float = 0.08
    micro_pause_duration_mean: float = 0.05
    idle_flick_probability: float = 0.03


# ---------------------------------------------------------------------------
# Pre-built profiles
# ---------------------------------------------------------------------------

PROFILE_FAST = ClickTimingProfile(
    pre_click_pause_mean=0.02, pre_click_pause_std=0.01,
    hold_duration_mean=0.05, hold_duration_std=0.01,
    post_click_pause_mean=0.03, post_click_pause_std=0.01,
)

PROFILE_NORMAL = ClickTimingProfile()

PROFILE_CAUTIOUS = ClickTimingProfile(
    pre_click_pause_mean=0.12, pre_click_pause_std=0.04,
    hold_duration_mean=0.12, hold_duration_std=0.05,
    post_click_pause_mean=0.15, post_click_pause_std=0.06,
)

TYPING_FAST = TypingTimingProfile(
    base_interval_mean=0.07, base_interval_std=0.02,
    burst_probability=0.3,
)

TYPING_NORMAL = TypingTimingProfile()

TYPING_SLOW = TypingTimingProfile(
    base_interval_mean=0.22, base_interval_std=0.08,
    hesitation_probability=0.12,
)


# ---------------------------------------------------------------------------
# Delay execution helpers
# ---------------------------------------------------------------------------

def sleep_reaction_time(profile: Optional[MovementTimingProfile] = None) -> float:
    """
    Sleep for a human-like reaction time before initiating movement.

    Args:
        profile: MovementTimingProfile to draw from. Uses default if None.

    Returns:
        Actual sleep duration in seconds.
    """
    p = profile or MovementTimingProfile()
    delay = weibull_delay(p.reaction_time_scale, p.reaction_time_shape)
    delay = max(0.02, delay)  # never instant
    time.sleep(delay)
    return delay


def sleep_click_pre(profile: Optional[ClickTimingProfile] = None) -> float:
    """Sleep for pre-click pause. Returns duration."""
    p = profile or ClickTimingProfile()
    delay = gaussian_delay(p.pre_click_pause_mean, p.pre_click_pause_std, min_val=0.005)
    time.sleep(delay)
    return delay


def sleep_click_hold(profile: Optional[ClickTimingProfile] = None) -> float:
    """Sleep for click-hold duration. Returns duration."""
    p = profile or ClickTimingProfile()
    delay = log_normal_delay(p.hold_duration_mean, sigma=0.3)
    delay = max(0.02, min(0.5, delay))
    time.sleep(delay)
    return delay


def sleep_click_post(profile: Optional[ClickTimingProfile] = None) -> float:
    """Sleep for post-click pause. Returns duration."""
    p = profile or ClickTimingProfile()
    delay = gaussian_delay(p.post_click_pause_mean, p.post_click_pause_std, min_val=0.005)
    time.sleep(delay)
    return delay


def sleep_keystroke(profile: Optional[TypingTimingProfile] = None, in_burst: bool = False) -> float:
    """
    Sleep for an inter-keystroke interval.

    Args:
        profile: TypingTimingProfile to use. Default profile if None.
        in_burst: Whether currently in a fast-typing burst.

    Returns:
        Actual sleep duration.
    """
    p = profile or TypingTimingProfile()
    if in_burst:
        delay = gaussian_delay(p.burst_interval_mean, p.burst_interval_std, min_val=0.02)
    else:
        delay = gaussian_delay(p.base_interval_mean, p.base_interval_std, min_val=0.04)
    time.sleep(delay)
    return delay


def sleep_micro_pause(profile: Optional[MovementTimingProfile] = None) -> float:
    """Sleep for a mid-trajectory micro-pause. Returns duration."""
    p = profile or MovementTimingProfile()
    delay = gaussian_delay(p.micro_pause_duration_mean, 0.02, min_val=0.01)
    time.sleep(delay)
    return delay
