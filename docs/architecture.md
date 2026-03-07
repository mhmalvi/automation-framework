# Architecture Decision Record — automation_framework

## Overview

`automation_framework` is a modular Python automation framework that produces
natural, human-like keyboard and mouse interactions by integrating three
existing open-source motion libraries with a layered behavior engine.

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                 User Script / Demo                   │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│             BehaviorEngine (core/)                   │
│  Orchestrates timing, hesitation, idle flicks,       │
│  overshoot, reading pauses, workflow sequences       │
└────────┬──────────────────────────┬─────────────────┘
         │                          │
┌────────▼────────┐      ┌──────────▼──────────────┐
│  TypingEngine   │      │   InputController        │
│  (core/)        │      │   (core/)                │
│  Burst/hesitate │      │   PyAutoGUI primary       │
│  typos/correct  │      │   pydirectinput optional  │
└─────────────────┘      └──────────┬───────────────┘
                                    │
                         ┌──────────▼───────────────┐
                         │    MovementEngine         │
                         │    (core/)                │
                         │  Adapter dispatcher       │
                         │  Jitter + micro-pauses    │
                         └──┬─────┬──────┬───────────┘
                            │     │      │
              ┌─────────────▼┐ ┌──▼───┐ ┌▼─────────────┐
              │human_mouse   │ │pyclick│ │humancursor    │
              │_adapter      │ │_adapter│ │_adapter      │
              └──────────────┘ └───────┘ └──────────────┘
                      ↕               ↕              ↕
              human-mouse lib   PyClick lib   HumanCursor lib

┌─────────────────────────────────────────────────────┐
│                 Vision Layer                         │
│  ScreenCapture → TemplateMatcher → ObjectDetector   │
│  (MSS + OpenCV)                                      │
└────────────────────────┬────────────────────────────┘
                         │ target coordinates
                         ▼
                   MovementEngine
```

---

## Key Design Decisions

### ADR-001: Adapter Pattern for Movement Libraries

**Context:** Three motion libraries (human_mouse, PyClick, HumanCursor) each
have different APIs. We need a unified interface while supporting all three.

**Decision:** Implement the Adapter pattern. Each library gets a wrapper class
implementing `BaseMovementAdapter` (abstract base). `MovementEngine` selects
adapters based on config and availability.

**Consequences:**
- Adding a new library requires only a new adapter class
- Graceful degradation when libraries aren't installed
- Runtime adapter switching without restarting the process

---

### ADR-002: "all" Mode with Fallback Chain

**Context:** Not all libraries may be installed. We want the system to work
with whatever is available.

**Decision:** When `adapter = "all"`, the engine builds an ordered list of
available adapters. The first available adapter in the chain is used. The
order is configurable via `movement.fallback_chain` in config.

**Consequences:**
- System works even with only one library installed
- Behavior is predictable and deterministic based on chain order
- Users can experiment by changing the chain order

---

### ADR-003: Statistical Timing Models Over Simple random.uniform()

**Context:** Using uniform random delays is clearly artificial — humans don't
exhibit uniform timing distributions.

**Decision:** Use scientifically-informed distributions:
- **Gaussian** — keystroke intervals (central limit theorem applies)
- **Weibull (k=1.5)** — reaction times (right-skewed, models human RT research)
- **Log-normal** — click hold durations (multiplicative process)
- **Poisson** — count of hesitation events in a session

**Consequences:**
- More realistic output but slightly more complex implementation
- Parameters are tunable via `TypingTimingProfile` / `ClickTimingProfile`

---

### ADR-004: Separate BehaviorEngine from InputController

**Context:** Input execution (pyautogui calls) and behavioral orchestration
(timing strategy, hesitation logic) are different concerns.

**Decision:** `InputController` handles raw execution (move, click, drag,
type). `BehaviorEngine` wraps it with behavioral overlays. `TypingEngine`
is a third orthogonal concern handling keystroke-level typing simulation.

**Consequences:**
- Each layer is independently testable
- Users can use `InputController` directly for performance-critical scripts
  where behavior simulation isn't needed
- `BehaviorEngine` can be extended without touching input execution

---

### ADR-005: MSS + OpenCV for Vision (Not PyAutoGUI.screenshot)

**Context:** PyAutoGUI's screenshot uses PIL which is slower (~40–80ms per
frame on typical screens). MSS uses direct OS-level APIs for capture.

**Decision:** Use MSS for screen capture (5–15ms per full frame) and OpenCV
for all image processing. Expose a `ScreenCapture` abstraction so backends
could be swapped.

**Consequences:**
- Significantly faster capture enables real-time detection loops
- OpenCV dependency is heavy (~50MB) but industry standard
- Vision layer degrades gracefully if OpenCV/MSS not installed

---

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `utils/randomness.py` | Statistical distributions, position jitter, probability helpers |
| `utils/timing_models.py` | Timing profile dataclasses, sleep helper functions |
| `utils/config_loader.py` | YAML/JSON config loading, dot-notation access, singleton |
| `core/movement_engine.py` | Abstract adapter interface + adapter dispatcher |
| `movement_adapters/*.py` | Per-library adapters (human_mouse, pyclick, humancursor) |
| `core/input_controller.py` | Raw input execution via PyAutoGUI / pydirectinput |
| `core/typing_engine.py` | Keystroke simulation, typos, bursts, hesitation |
| `core/behavior_engine.py` | High-level behavior orchestration, workflow execution |
| `vision/screen_capture.py` | MSS-based fast screen capture, region capture |
| `vision/template_matching.py` | OpenCV template matching, multi-scale, wait_for |
| `vision/object_detection.py` | Color detection, shape detection, change detection |

---

## Extension Points

1. **New motion library:** Add `movement_adapters/my_lib_adapter.py` implementing `BaseMovementAdapter`, register in `MovementEngine._build_adapter_chain()`.

2. **New timing profile:** Add a `TypingTimingProfile` or `ClickTimingProfile` instance to the profile dictionaries in `typing_engine.py` / `input_controller.py`.

3. **New vision detector:** Add a method to `ObjectDetector` or create a new class in `vision/`.

4. **Behavior plugin:** Create a subclass of `BehaviorEngine` overriding specific methods for application-specific behavior patterns.
