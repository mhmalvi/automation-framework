"""
gui.py — Full automation builder for non-technical users.

Supports: click, type, hotkey, scroll, wait, find-image-and-click,
          wait-for-image, take-screenshot, and region capture tool.
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).parent))

# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------

ACTION_TYPES = [
    # Coordinate-based
    "Click", "Double Click", "Right Click", "Scroll",
    # Vision-based
    "Find Image & Click", "Find Image & Double Click",
    "Find Image & Right Click", "Wait for Image",
    # Keyboard
    "Type Text", "Hotkey",
    # Window management
    "Focus Window", "Minimize Window", "Maximize Window", "Close Window",
    "Type to Window (Background)",
    # Utility
    "Wait", "Take Screenshot",
]

WINDOW_ACTIONS = {
    "Focus Window", "Minimize Window", "Maximize Window", "Close Window",
    "Type to Window (Background)",
}

VISION_ACTIONS = {
    "Find Image & Click", "Find Image & Double Click",
    "Find Image & Right Click", "Wait for Image",
}

SCROLL_DIRS = ["down", "up"]

# ---------------------------------------------------------------------------
# Diagnose adapters
# ---------------------------------------------------------------------------

def _diagnose_adapters() -> str:
    lines = []
    tests = [
        ("human_mouse", "from human_mouse import MouseController; MouseController()"),
        ("pyclick",     "from pyclick import HumanClicker, HumanCurve; HumanClicker()"),
        ("humancursor", "from humancursor import SystemCursor; SystemCursor()"),
        ("opencv",      "import cv2"),
        ("mss",         "import mss"),
    ]
    for name, code in tests:
        try:
            exec(code)
            lines.append(f"{name}: OK")
        except Exception as exc:
            lines.append(f"{name}: FAILED — {exc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workflow runner
# ---------------------------------------------------------------------------

def _run_workflow(actions: list, status_cb, running_flag: list):
    """Execute the workflow. running_flag[0] is checked to support stop."""
    try:
        from core.behavior_engine import BehaviorEngine
        from vision.template_matching import TemplateMatcher
        engine  = BehaviorEngine()
        matcher = TemplateMatcher()
        total   = len(actions)

        for i, action in enumerate(actions):
            if not running_flag[0]:
                status_cb("Stopped.")
                return

            atype = action["type"]
            status_cb(f"Step {i+1}/{total}: {atype}...")

            # ---- Coordinate-based ----
            if atype in ("Click", "Double Click", "Right Click"):
                x, y = int(action["x"]), int(action["y"])
                if atype == "Click":
                    engine.human_click(x, y)
                elif atype == "Double Click":
                    engine.human_double_click(x, y)
                else:
                    engine.human_right_click(x, y)

            elif atype == "Scroll":
                engine.human_scroll(int(action["x"]), int(action["y"]),
                                    direction=action["direction"])

            # ---- Vision-based ----
            elif atype in ("Find Image & Click", "Find Image & Double Click",
                           "Find Image & Right Click"):
                template = action["template"]
                confidence = float(action.get("confidence", 0.85))
                timeout    = float(action.get("timeout", 10.0))
                status_cb(f"Step {i+1}/{total}: Searching for {Path(template).name}...")
                result = matcher.wait_for(template, timeout=timeout,
                                          confidence=confidence)
                if result is None:
                    raise RuntimeError(
                        f"Image not found on screen: {Path(template).name}\n"
                        f"(confidence={confidence}, timeout={timeout}s)"
                    )
                x, y, conf = result
                status_cb(f"Step {i+1}/{total}: Found at ({x},{y}) conf={conf:.2f}, clicking...")
                if atype == "Find Image & Click":
                    engine.human_click(x, y)
                elif atype == "Find Image & Double Click":
                    engine.human_double_click(x, y)
                else:
                    engine.human_right_click(x, y)

            elif atype == "Wait for Image":
                template   = action["template"]
                confidence = float(action.get("confidence", 0.85))
                timeout    = float(action.get("timeout", 15.0))
                status_cb(f"Step {i+1}/{total}: Waiting for {Path(template).name}...")
                result = matcher.wait_for(template, timeout=timeout,
                                          confidence=confidence)
                if result is None:
                    raise RuntimeError(
                        f"Timed out waiting for: {Path(template).name}"
                    )

            # ---- Keyboard ----
            elif atype == "Type Text":
                engine.human_type(action["text"])

            elif atype == "Hotkey":
                keys = [k.strip() for k in action["keys"].split("+") if k.strip()]
                engine.human_hotkey(*keys)

            # ---- Window management ----
            elif atype in ("Focus Window", "Minimize Window",
                           "Maximize Window", "Close Window",
                           "Type to Window (Background)"):
                from utils.window_manager import (
                    focus_window, minimize_window, maximize_window,
                    close_window, append_text_to_window,
                )
                title = action["window_title"]
                if atype == "Focus Window":
                    if not focus_window(title):
                        raise RuntimeError(f"Window not found: '{title}'")
                elif atype == "Minimize Window":
                    minimize_window(title)
                elif atype == "Maximize Window":
                    maximize_window(title)
                elif atype == "Close Window":
                    close_window(title)
                elif atype == "Type to Window (Background)":
                    if not append_text_to_window(title, action.get("text", "")):
                        raise RuntimeError(
                            f"Could not type to window '{title}'.\n"
                            f"Window not found or has no standard edit control.\n"
                            f"Use 'Focus Window' + 'Type Text' instead."
                        )

            # ---- Utility ----
            elif atype == "Wait":
                time.sleep(float(action["seconds"]))

            elif atype == "Take Screenshot":
                from vision.screen_capture import ScreenCapture
                cap  = ScreenCapture()
                path = action.get("path", "screenshot.png")
                cap.save(cap.capture(), path)
                status_cb(f"Screenshot saved: {path}")

        status_cb(f"Done! ({total} step{'s' if total != 1 else ''} completed)")

    except Exception as exc:
        status_cb(f"Error: {exc}")


# ---------------------------------------------------------------------------
# Region capture — lets users draw a selection on-screen to save a template
# ---------------------------------------------------------------------------

class RegionCapture(tk.Toplevel):
    """
    Full-screen transparent overlay. User drags to select a region.
    Saves the selected region as a PNG template file.
    """

    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self._on_saved = on_saved
        self._start_x = self._start_y = 0
        self._rect = None

        # Full-screen, transparent, always on top
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.3)
        self.attributes("-topmost", True)
        self.configure(bg="black")
        self.overrideredirect(True)

        self._canvas = tk.Canvas(self, cursor="cross", bg="black",
                                  highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        lbl = tk.Label(self._canvas,
                       text="Drag to select the area you want to capture as a template.\n"
                            "Press Escape to cancel.",
                       bg="black", fg="white",
                       font=("Segoe UI", 14))
        lbl.place(relx=0.5, rely=0.05, anchor="center")

        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda _: self.destroy())

    def _on_press(self, e):
        self._start_x, self._start_y = e.x, e.y
        if self._rect:
            self._canvas.delete(self._rect)
        self._rect = self._canvas.create_rectangle(
            e.x, e.y, e.x, e.y,
            outline="red", width=2,
        )

    def _on_drag(self, e):
        self._canvas.coords(self._rect,
                             self._start_x, self._start_y, e.x, e.y)

    def _on_release(self, e):
        x1 = min(self._start_x, e.x)
        y1 = min(self._start_y, e.y)
        x2 = max(self._start_x, e.x)
        y2 = max(self._start_y, e.y)

        if (x2 - x1) < 10 or (y2 - y1) < 10:
            messagebox.showwarning("Too small",
                                   "Selection too small. Try again.",
                                   parent=self)
            return

        self.destroy()

        # Ask where to save
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG image", "*.png")],
            title="Save template as...",
            initialfile="template.png",
        )
        if not path:
            return

        try:
            import mss
            import cv2
            import numpy as np
            with mss.mss() as sct:
                monitor = {"left": x1, "top": y1,
                           "width": x2 - x1, "height": y2 - y1}
                raw   = sct.grab(monitor)
                frame = np.array(raw)[:, :, :3]
                cv2.imwrite(path, frame)
            if self._on_saved:
                self._on_saved(path)
        except Exception as exc:
            messagebox.showerror("Capture failed", str(exc))


# ---------------------------------------------------------------------------
# Add / Edit action dialog
# ---------------------------------------------------------------------------

class ActionDialog(tk.Toplevel):

    def __init__(self, parent, existing=None):
        super().__init__(parent)
        self.title("Add Action" if existing is None else "Edit Action")
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        self._parent  = parent
        self._existing = existing or {}
        self._type_var = tk.StringVar(value=self._existing.get("type", ACTION_TYPES[0]))

        ttk.Label(self, text="Action Type:").grid(row=0, column=0, sticky="w",
                                                   padx=12, pady=(12, 4))
        type_menu = ttk.Combobox(self, textvariable=self._type_var,
                                  values=ACTION_TYPES, state="readonly", width=26)
        type_menu.grid(row=0, column=1, sticky="w", padx=12, pady=(12, 4))
        type_menu.bind("<<ComboboxSelected>>", lambda _: self._refresh_fields())

        self._fields_frame = ttk.Frame(self)
        self._fields_frame.grid(row=1, column=0, columnspan=2, padx=12, pady=4)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(8, 12))
        ttk.Button(btn_frame, text="OK",     command=self._on_ok,    width=10).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy,   width=10).pack(side="left", padx=6)

        self._field_vars = {}
        self._refresh_fields()

    # ------------------------------------------------------------------
    # Field builders
    # ------------------------------------------------------------------

    def _clear_fields(self):
        for w in self._fields_frame.winfo_children():
            w.destroy()
        self._field_vars.clear()

    def _add_field(self, row, label, key, default=""):
        ttk.Label(self._fields_frame, text=label).grid(
            row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=self._existing.get(key, default))
        ttk.Entry(self._fields_frame, textvariable=var, width=32).grid(
            row=row, column=1, padx=(8, 0), pady=3)
        self._field_vars[key] = var

    def _add_combo(self, row, label, key, options, default=""):
        ttk.Label(self._fields_frame, text=label).grid(
            row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=self._existing.get(key, default))
        ttk.Combobox(self._fields_frame, textvariable=var, values=options,
                     state="readonly", width=30).grid(
            row=row, column=1, padx=(8, 0), pady=3)
        self._field_vars[key] = var

    def _add_image_field(self, row):
        """File picker row for template image path."""
        ttk.Label(self._fields_frame, text="Template image:").grid(
            row=row, column=0, sticky="w", pady=3)

        frame = ttk.Frame(self._fields_frame)
        frame.grid(row=row, column=1, padx=(8, 0), pady=3, sticky="w")

        var = tk.StringVar(value=self._existing.get("template", ""))
        entry = ttk.Entry(frame, textvariable=var, width=22)
        entry.pack(side="left")

        def browse():
            p = filedialog.askopenfilename(
                filetypes=[("PNG images", "*.png"), ("All images", "*.png;*.jpg;*.bmp")],
                title="Select template image",
            )
            if p:
                var.set(p)

        def capture():
            # Hide dialog, capture region, restore
            self.withdraw()
            time.sleep(0.3)

            def on_saved(path):
                var.set(path)
                self.deiconify()

            RegionCapture(self._parent, on_saved=on_saved)

        ttk.Button(frame, text="Browse", command=browse, width=7).pack(side="left", padx=2)
        ttk.Button(frame, text="Capture", command=capture, width=7).pack(side="left", padx=2)
        self._field_vars["template"] = var

    # ------------------------------------------------------------------

    def _refresh_fields(self):
        self._clear_fields()
        atype = self._type_var.get()

        if atype in ("Click", "Double Click", "Right Click"):
            self._add_field(0, "X coordinate:", "x", "500")
            self._add_field(1, "Y coordinate:", "y", "300")

        elif atype == "Scroll":
            self._add_field(0, "X coordinate:", "x", "500")
            self._add_field(1, "Y coordinate:", "y", "300")
            self._add_combo(2, "Direction:", "direction", SCROLL_DIRS, "down")

        elif atype in VISION_ACTIONS:
            self._add_image_field(0)
            self._add_field(1, "Confidence (0–1):", "confidence", "0.85")
            self._add_field(2, "Timeout (seconds):", "timeout", "10.0")

        elif atype == "Type Text":
            self._add_field(0, "Text to type:", "text", "")

        elif atype == "Hotkey":
            self._add_field(0, "Keys (e.g. ctrl+c):", "keys", "ctrl+c")

        elif atype in WINDOW_ACTIONS:
            self._add_field(0, "Window title contains:", "window_title", "Notepad")
            if atype == "Type to Window (Background)":
                self._add_field(1, "Text to send:", "text", "")
            ttk.Label(self._fields_frame,
                      text="(partial title match, case-insensitive)",
                      foreground="gray").grid(
                row=2 if atype == "Type to Window (Background)" else 1,
                column=0, columnspan=2, sticky="w", pady=(0, 4))

        elif atype == "Wait":
            self._add_field(0, "Seconds to wait:", "seconds", "1.0")

        elif atype == "Take Screenshot":
            self._add_field(0, "Save path:", "path", "screenshot.png")

    # ------------------------------------------------------------------

    def _on_ok(self):
        atype = self._type_var.get()
        data  = {"type": atype}
        try:
            if atype in ("Click", "Double Click", "Right Click"):
                data["x"] = int(self._field_vars["x"].get())
                data["y"] = int(self._field_vars["y"].get())

            elif atype == "Scroll":
                data["x"]         = int(self._field_vars["x"].get())
                data["y"]         = int(self._field_vars["y"].get())
                data["direction"] = self._field_vars["direction"].get()

            elif atype in VISION_ACTIONS:
                tmpl = self._field_vars["template"].get().strip()
                if not tmpl:
                    messagebox.showerror("Missing image",
                                         "Please select or capture a template image.",
                                         parent=self)
                    return
                if not Path(tmpl).exists():
                    messagebox.showerror("File not found",
                                         f"Template not found:\n{tmpl}",
                                         parent=self)
                    return
                data["template"]   = tmpl
                data["confidence"] = float(self._field_vars["confidence"].get())
                data["timeout"]    = float(self._field_vars["timeout"].get())

            elif atype == "Type Text":
                text = self._field_vars["text"].get()
                if not text:
                    messagebox.showerror("Error", "Text cannot be empty.", parent=self)
                    return
                data["text"] = text

            elif atype == "Hotkey":
                keys = self._field_vars["keys"].get().strip()
                if not keys:
                    messagebox.showerror("Error", "Keys cannot be empty.", parent=self)
                    return
                data["keys"] = keys

            elif atype in WINDOW_ACTIONS:
                title = self._field_vars["window_title"].get().strip()
                if not title:
                    messagebox.showerror("Error", "Window title cannot be empty.", parent=self)
                    return
                data["window_title"] = title
                if atype == "Type to Window (Background)":
                    data["text"] = self._field_vars["text"].get()

            elif atype == "Wait":
                data["seconds"] = float(self._field_vars["seconds"].get())

            elif atype == "Take Screenshot":
                data["path"] = self._field_vars["path"].get().strip() or "screenshot.png"

        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        self.result = data
        self.destroy()


# ---------------------------------------------------------------------------
# AI Agent window
# ---------------------------------------------------------------------------

class AIAgentWindow(tk.Toplevel):
    """
    AI-driven automation: user describes a goal in plain English,
    Claude sees the screen and decides what to do step by step.
    """

    DEFAULT_MODEL = "claude-haiku-4-5"

    def __init__(self, parent):
        super().__init__(parent)
        self.title("AI Agent — Claude Vision Automation")
        self.geometry("640x580")
        self.resizable(True, True)

        self._running_flag = [False]
        self._thread = None
        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)   # log row expands

        # ---- Row 0: API key ----
        ttk.Label(self, text="Anthropic API key:").grid(
            row=0, column=0, sticky="w", padx=10, pady=(12, 2))

        key_inner = ttk.Frame(self)
        key_inner.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        key_inner.columnconfigure(0, weight=1)

        self._key_var = tk.StringVar()
        self._key_entry = ttk.Entry(key_inner, textvariable=self._key_var, show="*")
        self._key_entry.grid(row=0, column=0, sticky="ew")

        def _toggle_show():
            self._key_entry.config(
                show="" if self._key_entry.cget("show") == "*" else "*")

        ttk.Button(key_inner, text="Show/Hide", command=_toggle_show, width=10).grid(
            row=0, column=1, padx=(6, 0))

        # ---- Row 2: Model + Max steps + Change detection ----
        opts_f = ttk.Frame(self)
        opts_f.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))

        ttk.Label(opts_f, text="Model:").pack(side="left")
        self._model_var = tk.StringVar(value=self.DEFAULT_MODEL)
        ttk.Combobox(opts_f, textvariable=self._model_var,
                     values=["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-6"],
                     state="readonly", width=20).pack(side="left", padx=(4, 12))

        ttk.Label(opts_f, text="Max steps:").pack(side="left")
        self._steps_var = tk.StringVar(value="30")
        ttk.Entry(opts_f, textvariable=self._steps_var, width=4).pack(side="left", padx=(4, 12))

        ttk.Label(opts_f, text="Change sensitivity:").pack(side="left")
        self._threshold_var = tk.StringVar(value="1")
        ttk.Combobox(opts_f, textvariable=self._threshold_var,
                     values=["0 (off)", "0.5", "1", "2", "5"],
                     width=8).pack(side="left", padx=(4, 12))
        ttk.Label(opts_f, text="%", foreground="gray").pack(side="left")

        ttk.Label(opts_f, text="  Wait timeout:").pack(side="left")
        self._ctimeout_var = tk.StringVar(value="8")
        ttk.Entry(opts_f, textvariable=self._ctimeout_var, width=3).pack(side="left", padx=(4, 0))
        ttk.Label(opts_f, text="s", foreground="gray").pack(side="left")

        # ---- Row 3: Goal + buttons ----
        goal_outer = ttk.LabelFrame(self, text="Goal — describe what you want the AI to do")
        goal_outer.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
        goal_outer.columnconfigure(0, weight=1)

        self._goal_text = tk.Text(goal_outer, height=4, wrap="word",
                                  font=("Segoe UI", 10))
        self._goal_text.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        self._goal_text.insert("1.0",
            "Open Notepad, type 'Hello from AI Agent!', "
            "then save the file as agent_test.txt on the Desktop.")

        btn_f = ttk.Frame(goal_outer)
        btn_f.grid(row=1, column=0, sticky="w", padx=6, pady=(0, 6))
        self._run_btn = ttk.Button(btn_f, text="Run AI Agent",
                                   command=self._run, width=16)
        self._stop_btn = ttk.Button(btn_f, text="Stop", command=self._stop,
                                    width=10, state="disabled")
        self._run_btn.pack(side="left", padx=(0, 4))
        self._stop_btn.pack(side="left")
        ttk.Label(btn_f,
                  text="  (Claude sees the full screen while running)",
                  foreground="gray").pack(side="left")

        # ---- Row 4: Log (expands) ----
        log_outer = ttk.LabelFrame(self, text="Agent log")
        log_outer.grid(row=4, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_outer.columnconfigure(0, weight=1)
        log_outer.rowconfigure(0, weight=1)

        self._log = tk.Text(log_outer, state="disabled", font=("Consolas", 9),
                            bg="#1e1e1e", fg="#d4d4d4", wrap="word")
        sb = ttk.Scrollbar(log_outer, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        self._log.grid(row=0, column=0, sticky="nsew", padx=(6, 0), pady=6)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)

    def _log_write(self, msg: str):
        self.after(0, self._do_log_write, msg)

    def _do_log_write(self, msg: str):
        self._log.config(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _run(self):
        api_key = self._key_var.get().strip()
        if not api_key:
            messagebox.showerror("API Key required",
                                 "Please enter your Anthropic API key.", parent=self)
            return

        goal = self._goal_text.get("1.0", "end").strip()
        if not goal:
            messagebox.showerror("Goal required",
                                 "Please describe what you want the AI to do.", parent=self)
            return

        try:
            max_steps = int(self._steps_var.get())
        except ValueError:
            max_steps = 30

        model = self._model_var.get()

        try:
            raw_thresh = self._threshold_var.get().split()[0]  # strip "(off)" label
            change_threshold = float(raw_thresh) / 100.0
        except (ValueError, IndexError):
            change_threshold = 0.01

        try:
            change_timeout = float(self._ctimeout_var.get())
        except ValueError:
            change_timeout = 8.0

        self._running_flag = [True]
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")

        # Clear log
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

        def worker():
            try:
                from utils.ai_agent import run_agent
                result = run_agent(
                    goal=goal,
                    api_key=api_key,
                    model=model,
                    max_steps=max_steps,
                    change_threshold=change_threshold,
                    change_timeout=change_timeout,
                    status_cb=self._log_write,
                    running_flag=self._running_flag,
                )
                self._log_write(f"\n=== {result} ===")
            except ImportError:
                self._log_write(
                    "ERROR: anthropic package not installed.\n"
                    "Run:  pip install anthropic\n"
                    "Then restart the application."
                )
            except Exception as exc:
                self._log_write(f"ERROR: {exc}")
            finally:
                self.after(0, self._after_run)

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def _stop(self):
        self._running_flag[0] = False
        self._log_write("Stop requested...")

    def _after_run(self):
        self._run_btn.config(state="normal")
        self._stop_btn.config(state="disabled")


# ---------------------------------------------------------------------------
# Coordinate picker
# ---------------------------------------------------------------------------

class CoordPicker(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Coordinate Picker")
        self.geometry("280x120")
        self.resizable(False, False)
        ttk.Label(self,
                  text="Move your mouse to the target position.\nCoordinates update live.",
                  justify="center").pack(pady=(12, 6))
        self._lbl = ttk.Label(self, text="X: ---   Y: ---",
                               font=("Consolas", 14, "bold"))
        self._lbl.pack(pady=4)
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=6)
        self._update()

    def _update(self):
        try:
            import pyautogui
            x, y = pyautogui.position()
            self._lbl.config(text=f"X: {x}   Y: {y}")
        except Exception:
            pass
        if self.winfo_exists():
            self.after(50, self._update)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Automation Framework")
        self.geometry("700x560")
        self.resizable(True, True)
        self._actions: list  = []
        self._running        = False
        self._running_flag   = [False]
        self._build_ui()

    def _build_ui(self):
        # ---- Toolbar row 1: step management ----
        tb1 = ttk.Frame(self)
        tb1.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Button(tb1, text="+ Add Step",   command=self._add_action).pack(side="left", padx=2)
        ttk.Button(tb1, text="Edit",         command=self._edit_action).pack(side="left", padx=2)
        ttk.Button(tb1, text="Delete",       command=self._delete_action).pack(side="left", padx=2)
        ttk.Button(tb1, text="Move Up",      command=self._move_up).pack(side="left", padx=2)
        ttk.Button(tb1, text="Move Down",    command=self._move_down).pack(side="left", padx=2)

        # ---- Toolbar row 2: tools ----
        tb2 = ttk.Frame(self)
        tb2.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Button(tb2, text="Find Coordinates", command=self._open_picker).pack(side="left", padx=2)
        ttk.Button(tb2, text="Capture Region",   command=self._capture_region).pack(side="left", padx=2)
        ttk.Button(tb2, text="Diagnose",         command=self._diagnose).pack(side="left", padx=2)
        ttk.Separator(tb2, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(tb2, text="AI Agent",
                   command=lambda: AIAgentWindow(self)).pack(side="left", padx=2)

        # ---- Step list ----
        lf = ttk.LabelFrame(self, text="Workflow Steps")
        lf.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("step", "action", "details")
        self._tree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("step",    text="#")
        self._tree.heading("action",  text="Action")
        self._tree.heading("details", text="Details")
        self._tree.column("step",    width=36, anchor="center")
        self._tree.column("action",  width=180)
        self._tree.column("details", width=420)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tree.bind("<Double-1>", lambda _: self._edit_action())

        # ---- Delay + Loop options ----
        df = ttk.Frame(self)
        df.pack(fill="x", padx=10, pady=2)
        ttk.Label(df, text="Delay before start (s):").pack(side="left")
        self._delay_var = tk.StringVar(value="3")
        ttk.Entry(df, textvariable=self._delay_var, width=5).pack(side="left", padx=(4, 16))

        self._loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(df, text="Loop", variable=self._loop_var,
                        command=self._on_loop_toggle).pack(side="left")

        self._max_time_label = ttk.Label(df, text="  Max duration (min, 0=forever):")
        self._max_time_var   = tk.StringVar(value="0")
        self._max_time_entry = ttk.Entry(df, textvariable=self._max_time_var, width=5)

        self._randomize_var = tk.BooleanVar(value=False)
        self._randomize_chk = ttk.Checkbutton(df, text="Randomize step order",
                                               variable=self._randomize_var)

        self._loop_delay_label = ttk.Label(df, text="  Delay between loops (s):")
        self._loop_delay_var   = tk.StringVar(value="1")
        self._loop_delay_entry = ttk.Entry(df, textvariable=self._loop_delay_var, width=5)

        # ---- Bottom bar ----
        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=10, pady=(4, 6))
        ttk.Button(bf, text="Save Workflow", command=self._save).pack(side="left", padx=2)
        ttk.Button(bf, text="Load Workflow", command=self._load).pack(side="left", padx=2)
        ttk.Separator(bf, orient="vertical").pack(side="left", fill="y", padx=8)
        self._run_btn  = ttk.Button(bf, text="RUN",  command=self._run,  width=12)
        self._stop_btn = ttk.Button(bf, text="Stop", command=self._stop, width=8, state="disabled")
        self._run_btn.pack(side="left", padx=2)
        self._stop_btn.pack(side="left", padx=2)

        # ---- Status ----
        self._status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self._status_var,
                  relief="sunken", anchor="w").pack(fill="x", padx=10, pady=(0, 6))

    # ------------------------------------------------------------------
    # Action list management
    # ------------------------------------------------------------------

    def _action_details(self, a: dict) -> str:
        t = a["type"]
        if t in ("Click", "Double Click", "Right Click"):
            return f"X={a['x']}, Y={a['y']}"
        if t == "Scroll":
            return f"X={a['x']}, Y={a['y']}, {a['direction']}"
        if t in VISION_ACTIONS:
            return f"{Path(a['template']).name}  (conf={a.get('confidence',0.85)}, timeout={a.get('timeout',10)}s)"
        if t == "Type Text":
            txt = a["text"]
            return txt if len(txt) <= 65 else txt[:62] + "..."
        if t == "Hotkey":
            return a["keys"]
        if t == "Wait":
            return f"{a['seconds']}s"
        if t in WINDOW_ACTIONS:
            detail = f"window='{a.get('window_title','')}'"
            if t == "Type to Window (Background)":
                txt = a.get("text", "")
                detail += f"  text='{txt[:40]}'" + ("..." if len(txt) > 40 else "")
            return detail
        if t == "Take Screenshot":
            return a.get("path", "screenshot.png")
        return ""

    def _refresh_list(self):
        self._tree.delete(*self._tree.get_children())
        for i, a in enumerate(self._actions, start=1):
            self._tree.insert("", "end", iid=str(i-1),
                               values=(i, a["type"], self._action_details(a)))

    def _selected_index(self) -> int:
        sel = self._tree.selection()
        return int(sel[0]) if sel else -1

    def _add_action(self):
        dlg = ActionDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self._actions.append(dlg.result)
            self._refresh_list()

    def _edit_action(self):
        idx = self._selected_index()
        if idx < 0:
            messagebox.showinfo("Select a step", "Click a step first.")
            return
        dlg = ActionDialog(self, existing=self._actions[idx])
        self.wait_window(dlg)
        if dlg.result:
            self._actions[idx] = dlg.result
            self._refresh_list()

    def _delete_action(self):
        idx = self._selected_index()
        if idx >= 0:
            del self._actions[idx]
            self._refresh_list()

    def _move_up(self):
        idx = self._selected_index()
        if idx <= 0:
            return
        self._actions[idx-1], self._actions[idx] = self._actions[idx], self._actions[idx-1]
        self._refresh_list()
        self._tree.selection_set(str(idx-1))

    def _move_down(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self._actions) - 1:
            return
        self._actions[idx], self._actions[idx+1] = self._actions[idx+1], self._actions[idx]
        self._refresh_list()
        self._tree.selection_set(str(idx+1))

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _on_loop_toggle(self):
        if self._loop_var.get():
            self._max_time_label.pack(side="left")
            self._max_time_entry.pack(side="left", padx=(4, 8))
            self._randomize_chk.pack(side="left", padx=(0, 8))
            self._loop_delay_label.pack(side="left")
            self._loop_delay_entry.pack(side="left", padx=4)
        else:
            self._max_time_label.pack_forget()
            self._max_time_entry.pack_forget()
            self._randomize_chk.pack_forget()
            self._loop_delay_label.pack_forget()
            self._loop_delay_entry.pack_forget()

    def _open_picker(self):
        CoordPicker(self)

    def _capture_region(self):
        self.withdraw()
        time.sleep(0.3)

        def on_saved(path):
            self.deiconify()
            self._status(f"Template saved: {path}")
            if messagebox.askyesno("Add step?",
                                   f"Template saved:\n{path}\n\nAdd a 'Find Image & Click' step now?",
                                   parent=self):
                self._actions.append({
                    "type":       "Find Image & Click",
                    "template":   path,
                    "confidence": 0.85,
                    "timeout":    10.0,
                })
                self._refresh_list()

        def on_cancel():
            self.deiconify()

        rc = RegionCapture(self, on_saved=on_saved)
        rc.bind("<Destroy>", lambda _: self.after(100, self.deiconify))

    def _diagnose(self):
        messagebox.showinfo("Adapter Diagnostics", _diagnose_adapters(), parent=self)

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    def _save(self):
        if not self._actions:
            messagebox.showinfo("Nothing to save", "Add some steps first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Workflow files", "*.json"), ("All files", "*.*")],
            title="Save Workflow",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._actions, f, indent=2)
            self._status("Saved: " + path)

    def _load(self):
        path = filedialog.askopenfilename(
            filetypes=[("Workflow files", "*.json"), ("All files", "*.*")],
            title="Load Workflow",
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._actions = json.load(f)
            self._refresh_list()
            self._status("Loaded: " + path)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _run(self):
        if not self._actions:
            messagebox.showinfo("Nothing to run", "Add some steps first.")
            return
        if self._running:
            return

        try:
            delay = float(self._delay_var.get())
        except ValueError:
            delay = 3.0

        self._running        = True
        self._running_flag   = [True]
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")

        loop       = self._loop_var.get()
        randomize  = self._randomize_var.get()
        try:
            max_minutes = float(self._max_time_var.get())
        except ValueError:
            max_minutes = 0
        try:
            loop_delay = float(self._loop_delay_var.get())
        except ValueError:
            loop_delay = 1.0

        def worker():
            # Countdown
            if delay > 0:
                for remaining in range(int(delay), 0, -1):
                    if not self._running_flag[0]:
                        self._status("Stopped.")
                        self._after_run()
                        return
                    self._status(f"Starting in {remaining}s...  switch to your target window now!")
                    time.sleep(1)

            if not self._running_flag[0]:
                self._status("Stopped.")
                self._after_run()
                return

            deadline = (time.time() + max_minutes * 60) if max_minutes > 0 else None
            loop_count = 0

            while True:
                # Build the step list for this iteration
                steps = list(self._actions)
                if randomize:
                    import random
                    random.shuffle(steps)

                loop_count += 1
                if loop:
                    elapsed = int(time.time() - (deadline - max_minutes * 60)) if deadline else 0
                    remaining_str = ""
                    if deadline:
                        left = max(0, int(deadline - time.time()))
                        remaining_str = f"  |  {left//60}m {left%60}s left"
                    self._status(f"Loop #{loop_count}{remaining_str}")

                _run_workflow(steps, self._status, self._running_flag)

                # Stop conditions
                if not self._running_flag[0]:
                    break
                if not loop:
                    break
                if deadline and time.time() >= deadline:
                    self._status(f"Time limit reached after {loop_count} loop(s).")
                    break

                # Delay between loops
                if loop_delay > 0:
                    for t in range(int(loop_delay * 10)):
                        if not self._running_flag[0]:
                            break
                        time.sleep(0.1)

            self._running = False
            self._after_run()

        threading.Thread(target=worker, daemon=True).start()

    def _stop(self):
        self._running        = False
        self._running_flag[0] = False

    def _after_run(self):
        self.after(0, lambda: self._run_btn.config(state="normal"))
        self.after(0, lambda: self._stop_btn.config(state="disabled"))

    def _status(self, msg: str):
        self.after(0, lambda: self._status_var.set(msg))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
