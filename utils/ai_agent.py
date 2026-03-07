"""
ai_agent.py — AI-driven automation via Claude vision API.

Optimisations:
  - Screenshots downscaled to max 960px wide, JPEG encoded (~10x smaller)
  - Coordinates auto-scaled back to full screen resolution
  - After each action, OpenCV frame-diff waits for screen to change
    before calling Claude — no wasted API calls on static screens
  - Model fallback: if chosen model is overloaded, switches to next and
    STAYS on it for the rest of the session (no re-trying dead models)
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Callable, List, Optional, Tuple

import cv2
import mss
import numpy as np

logger = logging.getLogger(__name__)

FALLBACK_CHAIN = ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"]

SYSTEM_PROMPT = """You are a Windows desktop automation agent controlling a real computer.

The screenshot is scaled down for efficiency. Use the pixel coordinates you see in the image — they will be automatically mapped to the real screen.

Respond with ONLY a single JSON object — no markdown, no explanation.

Available actions:
{"action": "click",        "x": <int>, "y": <int>}
{"action": "double_click", "x": <int>, "y": <int>}
{"action": "right_click",  "x": <int>, "y": <int>}
{"action": "type",         "text": "<string>"}
{"action": "hotkey",       "keys": "<combo e.g. win+r or ctrl+s>"}
{"action": "scroll",       "x": <int>, "y": <int>, "direction": "up"|"down"}
{"action": "focus_window", "title": "<partial title>"}
{"action": "done",         "message": "<what was accomplished>"}
{"action": "fail",         "reason": "<why impossible>"}

Rules:
- Click a text field before typing into it
- Use keyboard shortcuts where efficient (win+r, ctrl+s, alt+f4)
- When the goal is fully done, return done immediately
- Return ONLY valid JSON, nothing else
"""


# ---------------------------------------------------------------------------
# Screen helpers
# ---------------------------------------------------------------------------

def _capture_frame() -> np.ndarray:
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[0])
        return np.array(raw)[:, :, :3]


def _frame_to_b64(frame: np.ndarray, max_width: int = 960) -> Tuple[str, float, float]:
    """Downscale + JPEG encode. Returns (b64, scale_x, scale_y)."""
    h, w = frame.shape[:2]
    if w > max_width:
        nw = max_width
        nh = int(h * max_width / w)
        frame = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)
    sx = w / frame.shape[1]
    sy = h / frame.shape[0]
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.standard_b64encode(buf.tobytes()).decode(), sx, sy


def _frames_differ(a: np.ndarray, b: np.ndarray, threshold: float) -> bool:
    diff = cv2.absdiff(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY),
                       cv2.cvtColor(b, cv2.COLOR_BGR2GRAY))
    return np.count_nonzero(diff > 15) / diff.size >= threshold


def _wait_for_change(
    ref: np.ndarray,
    timeout: float,
    threshold: float,
    running_flag: list,
    status_cb: Callable,
) -> np.ndarray:
    if threshold <= 0:
        return _capture_frame()
    status_cb("  [waiting for screen to update...]")
    deadline = time.time() + timeout
    while time.time() < deadline and running_flag[0]:
        time.sleep(0.08)
        cur = _capture_frame()
        if _frames_differ(ref, cur, threshold):
            return cur
    return _capture_frame()


# ---------------------------------------------------------------------------
# Claude caller — sticky fallback
# ---------------------------------------------------------------------------

def _call_claude(
    client,
    messages: list,
    current_model: str,
    status_cb: Callable,
    running_flag: list,
) -> Tuple[str, list, str]:
    """
    Call Claude. If the current model is overloaded, try once more then
    permanently switch to the next model in the fallback chain.

    Returns (response_text, full_content_blocks, model_used).
    """
    import anthropic

    models_to_try: List[str] = []
    idx = FALLBACK_CHAIN.index(current_model) if current_model in FALLBACK_CHAIN else -1
    if idx >= 0:
        models_to_try = FALLBACK_CHAIN[idx:]          # current + all after
    else:
        models_to_try = [current_model] + FALLBACK_CHAIN  # unknown model, try all

    last_exc = None
    for mdl in models_to_try:
        use_thinking = mdl in ("claude-opus-4-6", "claude-sonnet-4-6")
        kwargs = dict(
            model=mdl,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        if use_thinking:
            kwargs["thinking"] = {"type": "adaptive"}

        # 2 quick retries per model before moving on
        for attempt in range(2):
            if not running_flag[0]:
                raise RuntimeError("stopped")
            try:
                with client.messages.stream(**kwargs) as stream:
                    text = "".join(stream.text_stream)
                    final = stream.get_final_message()
                if mdl != current_model:
                    status_cb(f"  [switched to {mdl}]")
                return text, final.content, mdl

            except anthropic.AuthenticationError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(2)   # one short pause then try again
                # attempt 1 failed → break to next model

        status_cb(f"  [{mdl} overloaded, trying next model...]")

    raise RuntimeError(f"All models overloaded: {last_exc}")


# ---------------------------------------------------------------------------
# Action executor
# ---------------------------------------------------------------------------

def _execute(action: dict, engine, sx: float, sy: float) -> str:
    from utils.window_manager import focus_window

    def X(v): return int(round(int(v) * sx))
    def Y(v): return int(round(int(v) * sy))

    t = action.get("action", "")
    if t == "click":
        engine.human_click(X(action["x"]), Y(action["y"]))
        return f"clicked ({X(action['x'])},{Y(action['y'])})"
    if t == "double_click":
        engine.human_double_click(X(action["x"]), Y(action["y"]))
        return f"double-clicked ({X(action['x'])},{Y(action['y'])})"
    if t == "right_click":
        engine.human_right_click(X(action["x"]), Y(action["y"]))
        return f"right-clicked ({X(action['x'])},{Y(action['y'])})"
    if t == "type":
        engine.human_type(action["text"])
        return f"typed: {action['text'][:50]}"
    if t == "hotkey":
        keys = [k.strip() for k in action["keys"].split("+") if k.strip()]
        engine.human_hotkey(*keys)
        return f"hotkey: {action['keys']}"
    if t == "scroll":
        engine.human_scroll(X(action["x"]), Y(action["y"]),
                            direction=action.get("direction", "down"))
        return f"scrolled {action.get('direction','down')}"
    if t == "focus_window":
        ok = focus_window(action.get("title", ""))
        return f"focus '{action.get('title','')}': {'ok' if ok else 'not found'}"
    return f"unknown: {t}"


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_agent(
    goal: str,
    api_key: str,
    model: str = "claude-haiku-4-5",
    max_steps: int = 30,
    change_threshold: float = 0.01,
    change_timeout: float = 8.0,
    status_cb: Callable[[str], None] = print,
    running_flag: Optional[list] = None,
) -> str:
    import anthropic

    if running_flag is None:
        running_flag = [True]

    client = anthropic.Anthropic(api_key=api_key)

    try:
        from core.behavior_engine import BehaviorEngine
        engine = BehaviorEngine()
    except Exception as exc:
        return f"BehaviorEngine init failed: {exc}"

    active_model = model
    messages: list = []
    current_frame = _capture_frame()
    step = 0

    status_cb(f"Goal: {goal}")
    status_cb(f"Model: {active_model}  |  Change threshold: {change_threshold*100:.1f}%")

    while running_flag[0] and step < max_steps:
        step += 1

        b64, sx, sy = _frame_to_b64(current_frame)
        messages.append({
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text",
                 "text": f"Goal: {goal}\nStep {step}/{max_steps} — next action? (JSON only)"},
            ],
        })

        status_cb(f"Step {step}/{max_steps}: asking Claude...")

        try:
            resp_text, content_blocks, active_model = _call_claude(
                client, messages, active_model, status_cb, running_flag)
        except RuntimeError as exc:
            if "stopped" in str(exc):
                return "Stopped by user."
            return str(exc)
        except Exception as exc:
            return f"API error: {exc}"

        messages.append({"role": "assistant", "content": content_blocks})

        # Parse JSON
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", resp_text.strip())
        action = None
        try:
            action = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{.*?\}", raw, re.DOTALL)
            if m:
                try:
                    action = json.loads(m.group())
                except json.JSONDecodeError:
                    pass
        if action is None:
            status_cb(f"  [bad JSON, retrying] {raw[:60]}")
            messages.append({"role": "user",
                             "content": "Invalid JSON. Reply with ONLY a JSON action object."})
            step -= 1   # don't count this as a real step
            continue

        atype = action.get("action", "")
        status_cb(f"  -> {atype}: {json.dumps(action)[:80]}")

        if atype == "done":
            return f"Done: {action.get('message','Task completed.')}"
        if atype == "fail":
            return f"Failed: {action.get('reason','Unknown.')}"

        # Execute
        try:
            ref = _capture_frame()
            result = _execute(action, engine, sx, sy)
            status_cb(f"     {result}")
        except Exception as exc:
            result = f"error: {exc}"
            status_cb(f"     ERROR: {exc}")
            ref = current_frame

        messages.append({"role": "user", "content": f"Result: {result}"})

        if not running_flag[0]:
            return "Stopped by user."

        current_frame = _wait_for_change(
            ref, change_timeout, change_threshold, running_flag, status_cb)

    return "Stopped by user." if not running_flag[0] else f"Reached max steps ({max_steps})."
