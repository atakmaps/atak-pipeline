"""Scale Tk window sizes to the user's display (small laptops → shrink, large monitors → grow).

Call sites pass "design" pixel sizes intended for a 1920×1080-class monitor. This module
scales proportionally to the available screen, clamps so the window fits within a margin
(taskbars / chrome), and centers the window.
"""
from __future__ import annotations

import tkinter as tk
from typing import Tuple

# Layout baseline matching typical design assumptions in this repo.
REF_SCREEN_W = 1920
REF_SCREEN_H = 1080
# Leave a margin so controls stay on-screen (title bar, panels, taskbars).
MARGIN_FRAC = 0.06
# Readability floor / cap so scaling stays reasonable on extremes.
MIN_SCALE = 0.52
MAX_SCALE = 1.35


def usable_screen_bounds(widget: tk.Misc) -> Tuple[int, int]:
    top = widget.winfo_toplevel()
    top.update_idletasks()
    sw = max(int(top.winfo_screenwidth()), 640)
    sh = max(int(top.winfo_screenheight()), 480)
    mx = max(320, int(sw * (1.0 - MARGIN_FRAC)))
    my = max(240, int(sh * (1.0 - MARGIN_FRAC)))
    return mx, my


def scale_factor(widget: tk.Misc) -> float:
    mx, my = usable_screen_bounds(widget)
    raw = min(mx / REF_SCREEN_W, my / REF_SCREEN_H)
    return max(MIN_SCALE, min(MAX_SCALE, raw))


def scaled_dimensions(widget: tk.Misc, base_w: int, base_h: int) -> Tuple[int, int, float]:
    mx, my = usable_screen_bounds(widget)
    s = scale_factor(widget)
    w = int(round(base_w * s))
    h = int(round(base_h * s))
    w = max(320, min(w, mx))
    h = max(240, min(h, my))
    return w, h, s


def _place_center(widget: tk.Misc, w: int, h: int) -> None:
    top = widget.winfo_toplevel()
    sw = max(int(top.winfo_screenwidth()), w)
    sh = max(int(top.winfo_screenheight()), h)
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    widget.geometry(f"{w}x{h}+{x}+{y}")


def apply_fixed_size_window(win: tk.Wm, base_w: int, base_h: int) -> float:
    """Fixed-size dialogs (resizable False). Returns scale for wraplength etc."""
    win.update_idletasks()
    w, h, s = scaled_dimensions(win, base_w, base_h)
    _place_center(win, w, h)
    try:
        win.minsize(w, h)
        win.maxsize(w, h)
    except tk.TclError:
        pass
    return s


def apply_resizable_window(win: tk.Wm, base_w: int, base_h: int, base_minsize: Tuple[int, int]) -> float:
    """Resizable main windows; initial geometry scaled; minsize scaled (clamped)."""
    win.update_idletasks()
    w, h, s = scaled_dimensions(win, base_w, base_h)
    _place_center(win, w, h)
    mw = int(round(base_minsize[0] * s))
    mh = int(round(base_minsize[1] * s))
    mw = max(280, min(mw, w))
    mh = max(200, min(mh, h))
    try:
        win.minsize(mw, mh)
    except tk.TclError:
        pass
    return s


def scaled_int(base_px: int, scale: float) -> int:
    return max(80, int(round(base_px * scale)))
