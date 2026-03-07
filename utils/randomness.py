"""
randomness.py — Statistical distributions for human-like variability.

Provides non-uniform random functions used across the framework to simulate
realistic human variance in timing, position, and behavior.
"""

import math
import random
from typing import Tuple


# ---------------------------------------------------------------------------
# Scalar generators
# ---------------------------------------------------------------------------

def gaussian_delay(mean: float, std: float, min_val: float = 0.0, max_val: float = float("inf")) -> float:
    """
    Return a Gaussian-distributed delay clamped to [min_val, max_val].

    Args:
        mean: Center of the distribution (seconds).
        std: Standard deviation (seconds).
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.

    Returns:
        Sampled delay in seconds.
    """
    value = random.gauss(mean, std)
    return max(min_val, min(max_val, value))


def weibull_delay(scale: float, shape: float = 1.5) -> float:
    """
    Return a Weibull-distributed delay, good for reaction-time modeling.

    Args:
        scale: Scale parameter (lambda). Roughly the median value.
        shape: Shape parameter (k). 1.5 gives a right-skewed human RT profile.

    Returns:
        Sampled delay in seconds (always >= 0).
    """
    # Python's random.weibullvariate uses shape=k, scale=lambda
    return random.weibullvariate(scale, shape)


def poisson_event_count(lam: float) -> int:
    """
    Return a Poisson-distributed count, used for modeling hesitation events.

    Args:
        lam: Expected number of events (lambda).

    Returns:
        Non-negative integer event count.
    """
    # Manual Knuth algorithm for small lambda
    L = math.exp(-lam)
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


def uniform_jitter(magnitude: float) -> float:
    """
    Return a symmetric uniform jitter in [-magnitude, +magnitude].

    Args:
        magnitude: Max absolute deviation.

    Returns:
        Float jitter value.
    """
    return random.uniform(-magnitude, magnitude)


def log_normal_delay(mean: float, sigma: float = 0.3) -> float:
    """
    Return a log-normal delay. Good for click/reaction latency modeling.

    Args:
        mean: Desired mean of the distribution (seconds).
        sigma: Shape parameter. Smaller = tighter, larger = more spread.

    Returns:
        Positive float delay in seconds.
    """
    mu = math.log(mean) - (sigma ** 2) / 2
    return random.lognormvariate(mu, sigma)


# ---------------------------------------------------------------------------
# Position jitter
# ---------------------------------------------------------------------------

def jitter_position(x: float, y: float, radius: float = 3.0) -> Tuple[float, float]:
    """
    Apply circular random jitter to a screen coordinate.

    Simulates imprecise human cursor landing near—but not exactly on—a target.

    Args:
        x: Target x coordinate.
        y: Target y coordinate.
        radius: Maximum pixel radius of jitter.

    Returns:
        (jittered_x, jittered_y) as floats.
    """
    angle = random.uniform(0, 2 * math.pi)
    # Use sqrt for uniform distribution within circle (not just on edge)
    r = radius * math.sqrt(random.random())
    return x + r * math.cos(angle), y + r * math.sin(angle)


def jitter_position_gaussian(x: float, y: float, std: float = 2.0) -> Tuple[float, float]:
    """
    Apply Gaussian jitter to a screen coordinate (more human-like than uniform).

    Args:
        x: Target x coordinate.
        y: Target y coordinate.
        std: Standard deviation in pixels for both axes.

    Returns:
        (jittered_x, jittered_y) as floats.
    """
    return (
        x + random.gauss(0, std),
        y + random.gauss(0, std),
    )


# ---------------------------------------------------------------------------
# Probability helpers
# ---------------------------------------------------------------------------

def chance(probability: float) -> bool:
    """
    Return True with the given probability.

    Args:
        probability: Float in [0.0, 1.0].

    Returns:
        bool.
    """
    return random.random() < probability


def weighted_choice(options: list, weights: list):
    """
    Choose one item from options using relative weights.

    Args:
        options: List of items to choose from.
        weights: Corresponding positive weights (need not sum to 1).

    Returns:
        Selected item.
    """
    return random.choices(options, weights=weights, k=1)[0]
