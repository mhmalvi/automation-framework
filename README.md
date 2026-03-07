# automation_framework

A professional-grade Python automation framework for Windows 10/11 that produces natural, human-like keyboard and mouse interactions.

Integrates and extends three open-source motion libraries — **human_mouse**, **PyClick**, and **HumanCursor** — with a modular behavior engine, statistical timing models, and an OpenCV vision layer.

---

## Features

- **Unified movement API** — three human-like cursor motion libraries behind a single interface with runtime adapter switching and automatic fallback
- **Statistical timing** — Gaussian, Weibull, log-normal, and Poisson distributions for realistic delays (not `random.uniform`)
- **Behavior engine** — overshoot + self-correction, idle micro-flicks, hesitation, reading pauses, think pauses, workflow orchestration
- **Typing simulation** — burst patterns, mid-word hesitation, QWERTY-aware typo injection with realistic backspace correction
- **Vision layer** — MSS fast screen capture + OpenCV template matching, color detection, shape detection, and change detection
- **Config-driven** — YAML/JSON config with hot-override via `cfg.set()`
- **Graceful degradation** — works with whichever subset of optional libraries is installed

---

## Architecture

```
BehaviorEngine
├── TypingEngine          (keystroke simulation)
├── InputController       (PyAutoGUI / pydirectinput)
│   └── MovementEngine    (adapter dispatcher)
│       ├── HumanMouseAdapter   → human-mouse lib
│       ├── PyClickAdapter      → pyclick lib
│       └── HumanCursorAdapter  → humancursor lib
└── Vision
    ├── ScreenCapture     (MSS)
    ├── TemplateMatcher   (OpenCV)
    └── ObjectDetector    (OpenCV)
```

See [docs/architecture.md](docs/architecture.md) for detailed ADRs.

---

## Installation

```bash
pip install -r requirements.txt
```

**Python 3.10+ required. Designed for Windows 10/11.**

---

## Quick Start

```python
from core.behavior_engine import BehaviorEngine

engine = BehaviorEngine()

# Human-like click
engine.human_click(500, 300)

# Natural typing
engine.human_type("Hello, automation world!")

# Vision-driven click
from vision.template_matching import TemplateMatcher
matcher = TemplateMatcher()
result = matcher.find("templates/button.png")
if result:
    engine.human_click(result[0], result[1])
```

---

## Demos

```bash
python examples/natural_click_demo.py     # cursor movement
python examples/realistic_typing_demo.py  # typing (open text editor first)
python examples/vision_auto_click_demo.py # vision pipeline
```

---

## Tests

```bash
pytest --cov=. --cov-report=term-missing
```

---

## Documentation

- [Usage Guide](docs/usage.md)
- [Architecture Decisions](docs/architecture.md)
- [Configuration Reference](automation_config.yaml)

---

## Libraries Integrated

| Library | Role |
|---------|------|
| [human-mouse](https://github.com/sarperavci/human_mouse) | Bezier-interpolated curved paths |
| [PyClick](https://github.com/patrikoss/pyclick) | Configurable Bezier control points |
| [HumanCursor](https://github.com/riflosnake/HumanCursor) | Fitts's Law-based natural motion |
| [PyAutoGUI](https://github.com/asweigart/pyautogui) | Input execution layer |
| [MSS](https://github.com/BoboTiG/python-mss) | Fast screen capture |
| [OpenCV](https://opencv.org) | Computer vision |

---

## License

MIT
