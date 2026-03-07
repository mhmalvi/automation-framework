# Usage Guide — automation_framework

## Installation

```bash
# Python 3.10+ required
pip install -r requirements.txt

# Or install from pyproject.toml (editable dev mode)
pip install -e ".[dev]"

# With pydirectinput support for DirectX/games
pip install -e ".[directinput]"
```

---

## Quick Start

### 1. Simple human-like click

```python
from core.behavior_engine import BehaviorEngine

engine = BehaviorEngine()
engine.human_click(800, 400)          # move + click at (800, 400)
engine.human_double_click(800, 400)   # double-click
engine.human_right_click(800, 400)    # right-click with hesitation
```

### 2. Natural typing

```python
from core.typing_engine import TypingEngine

typer = TypingEngine()
typer.type("Hello, world!")                      # normal profile
typer.type("Fast message", profile_name="fast")  # fast typist
typer.type("Careful entry", profile_name="slow") # hunt-and-peck
```

### 3. Vision-driven automation

```python
from vision.template_matching import TemplateMatcher
from core.behavior_engine import BehaviorEngine

matcher = TemplateMatcher()
engine  = BehaviorEngine()

# Find a button by screenshot template
result = matcher.find("templates/submit_button.png", confidence=0.90)
if result:
    x, y, confidence = result
    print(f"Button at ({x}, {y}), confidence: {confidence:.2f}")
    engine.human_click(x, y)
```

### 4. Full workflow with reading pauses

```python
from core.behavior_engine import BehaviorEngine

engine = BehaviorEngine()

engine.perform_workflow([
    lambda: engine.human_click(200, 150),          # click search box
    lambda: engine.human_type("automation tools"),  # type query
    lambda: engine.human_key_press("enter"),        # submit
    lambda: engine.reading_pause(content_length=500),  # read results
    lambda: engine.human_click(400, 300),           # click first result
])
```

---

## Configuration

Copy `automation_config.yaml` to your working directory and edit:

```yaml
movement:
  adapter: "all"              # or "human_mouse" / "pyclick" / "humancursor"
  fallback_chain:
    - "human_mouse"
    - "pyclick"
    - "humancursor"
  landing_jitter_std: 2.5     # pixel jitter on landing (set 0 to disable)

behavior:
  click_profile: "normal"     # "fast" | "normal" | "cautious"
  typing_profile: "normal"    # "fast" | "normal" | "slow"
  idle_flick_probability: 0.03

typing:
  enable_typos: true
  paste_threshold: 80         # chars; longer text is pasted via clipboard

vision:
  match_confidence: 0.85
  grayscale_matching: true
```

Or set values at runtime:

```python
from utils.config_loader import get_config

cfg = get_config()
cfg.set("movement.adapter", "pyclick")
cfg.set("behavior.click_profile", "fast")
cfg.set("typing.enable_typos", False)
```

---

## Movement Adapter Selection

| Mode | Behavior |
|------|----------|
| `"all"` | Uses first available adapter in `fallback_chain` |
| `"human_mouse"` | Uses only `human-mouse` (Bezier interpolation) |
| `"pyclick"` | Uses only PyClick (configurable Bezier control points) |
| `"humancursor"` | Uses only HumanCursor (Fitts's Law model) |

Switch at runtime:

```python
from core.movement_engine import MovementEngine

engine = MovementEngine()
print(engine.available_adapters)   # ['human_mouse', 'pyclick', 'humancursor']
engine.set_adapter("humancursor")  # switch
```

---

## Timing Profiles

### Click profiles

```python
from utils.timing_models import PROFILE_FAST, PROFILE_NORMAL, PROFILE_CAUTIOUS
from core.input_controller import InputController

ctrl = InputController()
ctrl.set_click_profile("fast")     # quick clicks
ctrl.set_click_profile("cautious") # slow, deliberate clicks
```

### Typing profiles

```python
from core.typing_engine import TypingEngine

typer = TypingEngine()
typer.type("text", profile_name="fast")    # burst typing
typer.type("text", profile_name="slow")    # hunt-and-peck
```

---

## Vision API

### Screen capture

```python
from vision.screen_capture import ScreenCapture

cap = ScreenCapture()
frame = cap.capture()                    # full screen (BGR ndarray)
gray  = cap.capture_gray()              # grayscale
region = cap.capture(region=(0,0,800,600))  # sub-region
cap.save(frame, "screenshot.png")
```

### Template matching

```python
from vision.template_matching import TemplateMatcher

matcher = TemplateMatcher()

# Single match
result = matcher.find("button.png")
# result = (center_x, center_y, confidence) or None

# All matches
results = matcher.find_all("icon.png", confidence=0.80)

# Multi-scale (for DPI variations)
result = matcher.find_multiscale("logo.png", scales=[0.8, 1.0, 1.2])

# Wait until visible
result = matcher.wait_for("dialog.png", timeout=15.0)
```

### Object detection

```python
from vision.object_detection import ObjectDetector

detector = ObjectDetector()

# Find red regions
boxes = detector.find_by_color(
    lower_bgr=(0, 0, 180),
    upper_bgr=(80, 80, 255),
)
for box in boxes:
    cx, cy = detector.center_of_box(box)

# Find rectangular UI elements
rects = detector.find_rectangles(min_area=500)

# Detect screen changes
frame_a = cap.capture()
# ... do something ...
frame_b = cap.capture()
changed = detector.detect_change(frame_a, frame_b)
```

---

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=. --cov-report=term-missing

# Specific file
pytest tests/test_movement_models.py -v
pytest tests/test_behavior_patterns.py -v
```

---

## Running Demos

Open a text editor or browser before running demos.

```bash
# Mouse movement demo
python examples/natural_click_demo.py

# Typing simulation demo (open a text editor first)
python examples/realistic_typing_demo.py

# Vision-driven automation demo
python examples/vision_auto_click_demo.py
```

All demos start with a 3–5 second delay so you can position your environment.
Press **Ctrl+C** at any time to abort.

---

## Safety

- PyAutoGUI **FAILSAFE** is enabled by default — move the mouse to the
  top-left corner of the screen to abort any running automation.
- All delays have minimum values so the system never executes actions
  instantaneously (which would be inhuman).
- The framework does not bypass OS-level security mechanisms.
