#!/usr/bin/env python3
"""
ATAK USGS Orthophoto Downloader
- State selection first
- Zoom selection second
- Zoom screen: temporary (raw) vs on-device SQLite estimates from bundled metadata
- Summary confirmation before output folder picker
- Zenity folder picker on Linux with Tk fallback
- Progress bar during download
- Safe re-run: skips tiles that already exist
- Auto-launches SQLite builder on completion

Output structure:
    <selected parent>/Imagery/State/zoom/x/y.jpg
"""

import json
import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
import tkinter as tk
from tkinter import filedialog, messagebox

APP_TITLE = "Imagery Downloader"
STATE_GEOJSON_URL = "https://eric.clst.org/assets/wiki/uploads/Stuff/gz_2010_us_040_00_500k.json"
USGS_TILE_URL = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
USER_AGENT = "ATAK-Ortho-Downloader/1.1"

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BUNDLED_SCRIPT_DIR = Path(sys._MEIPASS) / "scripts"
else:
    BUNDLED_SCRIPT_DIR = Path(__file__).resolve().parent

if getattr(sys, "frozen", False):
    RUNTIME_STATE_DIR = Path(sys.executable).resolve().parent
else:
    RUNTIME_STATE_DIR = Path(__file__).resolve().parent

DATA_DIR = BUNDLED_SCRIPT_DIR / "data"
ZOOM_ESTIMATE_PATH = DATA_DIR / "zoom_estimates_z10_z16.json"
LAST_IMAGERY_ROOT_FILE = RUNTIME_STATE_DIR / ".last_imagery_root.txt"

# -----------------------------
# Logging
# -----------------------------

class Logger:
    def __init__(self) -> None:
        self.script_dir = Path(__file__).resolve().parent
        self.log_dir = self.script_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"atak_downloader_{ts}.log"
        self._fh = open(self.log_file, "a", encoding="utf-8", buffering=1)
        self.gui_queue: "queue.Queue[str]" = queue.Queue()

    def write(self, message: str) -> None:
        if not message.endswith("\n"):
            message += "\n"
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        try:
            sys.__stdout__.write(line)
            sys.__stdout__.flush()
        except Exception:
            pass
        try:
            self._fh.write(line)
            self._fh.flush()
        except Exception:
            pass
        try:
            self.gui_queue.put_nowait(line)
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


LOGGER = Logger()


def log(msg: str) -> None:
    LOGGER.write(msg)


def install_excepthook() -> None:
    def handle_exception(exc_type, exc_value, exc_tb):
        log("FATAL: Unhandled exception")
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log(tb)
        try:
            messagebox.showerror(APP_TITLE, f"Unhandled exception.\n\nLog file:\n{LOGGER.log_file}")
        except Exception:
            pass
    sys.excepthook = handle_exception


install_excepthook()

# -----------------------------
# Helpers
# -----------------------------

def human_bytes(num_bytes: int) -> str:
    value = float(max(num_bytes, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(num_bytes)} B"


# Raw estimates size the full-resolution download; on-device ATAK imagery SQLite is typically
# much smaller than that working-set figure (single packaged DB vs loose tiles + padding).
DEVICE_INSTALL_BYTES_VS_RAW_ESTIMATE = 0.22


def estimate_device_sqlite_bytes(raw_tile_bytes_sum: int) -> int:
    """Approximate on-device imagery DB size vs bundled raw-download estimate (see ratio above)."""
    if raw_tile_bytes_sum <= 0:
        return 0
    return max(1, int(raw_tile_bytes_sum * DEVICE_INSTALL_BYTES_VS_RAW_ESTIMATE))


def load_zoom_estimates() -> Dict[str, Dict[str, Dict[str, int]]]:
    if not ZOOM_ESTIMATE_PATH.exists():
        raise FileNotFoundError(
            f"Missing zoom estimate file:\n{ZOOM_ESTIMATE_PATH}\n\n"
            f"Copy windows_build/data/ into this build source or bundle it first."
        )
    with open(ZOOM_ESTIMATE_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["states"]

# -----------------------------
# Tile math
# -----------------------------

def lonlat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    xtile = max(0, min(int(n) - 1, xtile))
    ytile = max(0, min(int(n) - 1, ytile))
    return xtile, ytile


def zoom_resolution_labels(z: int, latitude_deg: float = 39.0) -> str:
    equator_mpp = 156543.03392804097 / (2 ** z)
    local_mpp = equator_mpp * math.cos(math.radians(latitude_deg))
    local_ft = local_mpp * 3.28084
    return f"Zoom {z}  (~{equator_mpp:.2f} m/px equator, ~{local_ft:.1f} ft/px mid-US)"

# -----------------------------
# State boundaries
# -----------------------------

STATE_ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


def download_state_geojson(temp_dir: Path) -> Path:
    out_path = temp_dir / "us_states.geojson"
    log(f"Downloading state boundaries: {STATE_GEOJSON_URL}")
    with requests.get(STATE_GEOJSON_URL, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
    log(f"Saved state boundaries to {out_path}")
    return out_path


def load_states(geojson_path: Path) -> Dict[str, List[List[Tuple[float, float]]]]:
    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    states = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        name = props.get("NAME") or props.get("NAME10") or props.get("STATE_NAME")
        geom = feature.get("geometry", {})
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])

        rings: List[List[Tuple[float, float]]] = []
        if gtype == "Polygon":
            if coords:
                rings.append([(float(x), float(y)) for x, y in coords[0]])
        elif gtype == "MultiPolygon":
            for poly in coords:
                if poly:
                    rings.append([(float(x), float(y)) for x, y in poly[0]])

        if name and rings:
            states[name] = rings
    return states


def bbox_for_rings(rings: List[List[Tuple[float, float]]]) -> Tuple[float, float, float, float]:
    xs = []
    ys = []
    for ring in rings:
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)

# -----------------------------
# Geometry helpers
# -----------------------------

def point_in_ring(x: float, y: float, ring: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    x1, y1 = ring[0]
    for i in range(1, n + 1):
        x2, y2 = ring[i % n]
        if ((y1 > y) != (y2 > y)):
            xinters = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < xinters:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def point_in_state(lon: float, lat: float, rings: List[List[Tuple[float, float]]]) -> bool:
    return any(point_in_ring(lon, lat, ring) for ring in rings)


def tile_center_lonlat(x: int, y: int, z: int) -> Tuple[float, float]:
    n = 2.0 ** z
    lon_deg = (x + 0.5) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ((y + 0.5) / n))))
    lat_deg = math.degrees(lat_rad)
    return lon_deg, lat_deg

# -----------------------------
# UI
# -----------------------------

class StateSelectionDialog(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} - Select States")
        self.geometry("620x700")
        self.minsize(620, 700)
        self.resizable(False, False)
        self.configure(cursor="arrow")

        self.result_mode = ""
        self.result_states: List[str] = []

        frame = tk.Frame(self, padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame,
            text="Select imagery state(s) to download:",
            font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 8))

        note = (
            "Choose one or more specific states, or use Select All.\n"
            "The downloader will fetch imagery for every selected state."
        )
        tk.Label(frame, text=note, justify="left").pack(anchor="w", pady=(0, 10))

        list_frame = tk.Frame(frame)
        list_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_frame, highlightthickness=1, highlightbackground="gray70")
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas)

        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(cursor="arrow")
        scrollbar.pack(side="right", fill="y")

        self.vars: Dict[str, tk.BooleanVar] = {}
        for state_name in sorted(STATE_ABBR_TO_NAME.values()):
            var = tk.BooleanVar(value=False)
            self.vars[state_name] = var
            cb = tk.Checkbutton(inner, text=state_name, variable=var, anchor="w", justify="left")
            cb.pack(anchor="w")

        btns = tk.Frame(frame)
        btns.pack(fill="x", pady=(12, 0))
        tk.Button(btns, text="Select All", width=12, command=self.select_all).pack(side="left")
        tk.Button(btns, text="Cancel", width=12, command=self.cancel).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="OK", width=12, command=self.submit).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

    def select_all(self) -> None:
        self.result_mode = "all"
        for var in self.vars.values():
            var.set(True)

    def submit(self) -> None:
        selected = sorted([state for state, var in self.vars.items() if var.get()])
        if not selected:
            messagebox.showwarning(APP_TITLE, "Select at least one state.")
            return
        self.result_states = selected
        if self.result_mode != "all":
            self.result_mode = "specific"
        self.destroy()

    def cancel(self) -> None:
        self.result_mode = ""
        self.result_states = []
        self.destroy()


class ZoomDialog(tk.Tk):
    def __init__(self, selected_states: List[str], zoom_estimates: Dict[str, Dict[str, Dict[str, int]]]) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} - Select Zoom Levels")
        self.geometry("780x740")
        self.resizable(False, False)
        self.configure(cursor="arrow")

        self.result: List[int] = []
        self.go_back = False
        self.zoom_total_bytes: Dict[int, int] = {}
        self.zoom_total_tiles: Dict[int, int] = {}
        self.vars: Dict[int, tk.BooleanVar] = {}

        frame = tk.Frame(self, padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        note_wrap = 720

        tk.Label(
            frame,
            text="Selected states to be installed:",
            font=("Arial", 11, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        states_sorted = "\n".join(sorted(selected_states))
        states_row = tk.Frame(frame)
        states_row.pack(anchor="w", fill="x", pady=(0, 10))
        states_scroll = tk.Scrollbar(states_row)
        states_text = tk.Text(
            states_row,
            height=14,
            width=86,
            wrap="none",
            font=("Arial", 10),
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            yscrollcommand=states_scroll.set,
            cursor="arrow",
        )
        states_scroll.config(command=states_text.yview)
        states_text.pack(side="left", fill="x", expand=True)
        states_scroll.pack(side="right", fill="y")
        states_text.insert("1.0", states_sorted)
        states_text.configure(state="disabled")

        bg = frame.cget("bg")
        intro = tk.Text(
            frame,
            height=8,
            width=92,
            wrap="word",
            font=("Arial", 12),
            relief="flat",
            padx=0,
            pady=0,
            highlightthickness=0,
            borderwidth=0,
            bg=bg,
            cursor="arrow",
        )
        intro.tag_configure("title", font=("Arial", 11, "bold"))
        intro.tag_configure("note_label", font=("Arial", 12, "bold"))
        intro.tag_configure("note_body", font=("Arial", 12))
        intro.insert("end", "Select the zoom levels (resolution) to download.\n\n", "title")
        intro.insert("end", "NOTE:", "note_label")
        intro.insert(
            "end",
            " This is the RAW image size only, it will not take up this much space on your Android device. "
            "Ensure you have enough hard drive space to contain this imagery. "
            "You will be able to remove the raw imagery later once compiled and installed on your device.",
            "note_body",
        )
        intro.configure(state="disabled")
        intro.pack(anchor="w", fill="x", pady=(0, 8))

        self.temp_space_var = tk.StringVar(
            value="Estimated temporary space needed for selected zooms: select at least one zoom"
        )
        tk.Label(
            frame,
            textvariable=self.temp_space_var,
            font=("Arial", 11, "bold"),
            justify="left",
            wraplength=note_wrap,
            anchor="w",
        ).pack(anchor="w", fill="x", pady=(0, 4))

        self.device_var = tk.StringVar(
            value="Estimated space to be installed on device: select at least one zoom"
        )
        tk.Label(
            frame,
            textvariable=self.device_var,
            font=("Arial", 11, "bold"),
            justify="left",
            wraplength=note_wrap,
            anchor="w",
        ).pack(anchor="w", fill="x", pady=(0, 16))

        mid = tk.Frame(frame)
        mid.pack(fill="both", expand=True)
        checks = tk.Frame(mid)
        checks.place(relx=0.5, rely=0.5, anchor="center")

        for z in range(10, 17):
            total_tiles = 0
            total_bytes = 0
            for state_name in selected_states:
                state_info = zoom_estimates.get(state_name, {})
                zoom_info = state_info.get(str(z), {})
                total_tiles += int(zoom_info.get("estimated_tiles", 0))
                total_bytes += int(zoom_info.get("estimated_bytes", 0))

            self.zoom_total_tiles[z] = total_tiles
            self.zoom_total_bytes[z] = total_bytes

            var = tk.BooleanVar(value=False)
            self.vars[z] = var
            cb = tk.Checkbutton(
                checks,
                text=(
                    f"{zoom_resolution_labels(z)}   |   "
                    f"estimated tiles: {total_tiles:,}   |   "
                    f"estimated size: {human_bytes(total_bytes)}"
                ),
                variable=var,
                anchor="w",
                justify="left",
                command=self.update_size_label,
            )
            cb.pack(anchor="w")

        btns = tk.Frame(frame)
        btns.pack(fill="x", pady=(12, 0))
        tk.Button(btns, text="Back", width=12, command=self.back).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Select All", width=12, command=self.select_all).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Clear All", width=12, command=self.clear_all).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Cancel", width=12, command=self.cancel).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="OK", width=12, command=self.submit).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

    def select_all(self) -> None:
        for v in self.vars.values():
            v.set(True)
        self.update_size_label()

    def clear_all(self) -> None:
        for v in self.vars.values():
            v.set(False)
        self.update_size_label()

    def update_size_label(self) -> None:
        selected = [z for z, var in self.vars.items() if var.get()]
        if not selected:
            self.temp_space_var.set(
                "Estimated temporary space needed for selected zooms: select at least one zoom"
            )
            self.device_var.set(
                "Estimated space to be installed on device: select at least one zoom"
            )
            return
        total_bytes = sum(self.zoom_total_bytes[z] for z in selected)
        total_tiles = sum(self.zoom_total_tiles[z] for z in selected)
        device_bytes = estimate_device_sqlite_bytes(total_bytes)
        self.temp_space_var.set(
            f"Estimated temporary space needed for selected zooms: {human_bytes(total_bytes)}   |   "
            f"estimated tiles: {total_tiles:,}"
        )
        self.device_var.set(
            f"Estimated space to be installed on device: {human_bytes(device_bytes)}"
        )

    def back(self) -> None:
        self.go_back = True
        self.result = []
        self.destroy()

    def submit(self) -> None:
        self.result = sorted([z for z, var in self.vars.items() if var.get()])
        if not self.result:
            messagebox.showwarning(APP_TITLE, "Select at least one zoom level.")
            return
        self.destroy()

    def cancel(self) -> None:
        self.go_back = False
        self.result = []
        self.destroy()


class ProgressWindow(tk.Tk):
    def __init__(self, log_path: Path):
        super().__init__()
        self.title(f"{APP_TITLE} - Progress")
        self.geometry("860x560")
        self.configure(cursor="arrow")

        top = tk.Frame(self, padx=10, pady=10)
        top.pack(fill="x")

        self.status_var = tk.StringVar(value="Initializing...")
        self.counter_var = tk.StringVar(value="0 / 0")
        self.detail_var = tk.StringVar(value=f"Log: {log_path}")

        tk.Label(top, textvariable=self.status_var, font=("Arial", 11, "bold")).pack(anchor="w")
        tk.Label(top, textvariable=self.counter_var).pack(anchor="w", pady=(4, 0))
        tk.Label(top, textvariable=self.detail_var, fg="gray30").pack(anchor="w", pady=(4, 8))

        self.canvas = tk.Canvas(top, height=24, bg="white", highlightthickness=1, highlightbackground="gray70")
        self.canvas.configure(cursor="arrow")
        self.canvas.pack(fill="x")
        self.bar = self.canvas.create_rectangle(0, 0, 0, 24, fill="#4a90e2", width=0)
        self.bar_text = self.canvas.create_text(5, 12, anchor="w", text="0%")

        stats = tk.Frame(self, padx=10)
        stats.pack(fill="x", pady=(6, 6))

        self.stats_vars = {
            "downloaded": tk.StringVar(value="Downloaded: 0"),
            "existing": tk.StringVar(value="Existing: 0"),
            "failed": tk.StringVar(value="Failed: 0"),
            "missing": tk.StringVar(value="Missing: 0"),
        }
        for i, key in enumerate(("downloaded", "existing", "failed", "missing")):
            tk.Label(stats, textvariable=self.stats_vars[key], width=18, anchor="w").grid(row=0, column=i, sticky="w")

        log_frame = tk.Frame(self, padx=10, pady=10)
        log_frame.pack(fill="both", expand=True)

        self.text = tk.Text(log_frame, wrap="word")
        self.text.pack(side="left", fill="both", expand=True)

        scroll = tk.Scrollbar(log_frame, command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.config(yscrollcommand=scroll.set)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.closed = False
        self.completion_message = None
        self.error_message = None

    def append_log(self, line: str) -> None:
        self.text.insert("end", line)
        self.text.see("end")
        self.update_idletasks()

    def set_progress(self, completed: int, total: int) -> None:
        total = max(total, 1)
        pct = int((completed / total) * 100)
        self.counter_var.set(f"{completed} / {total}")
        width = max(self.canvas.winfo_width(), 1)
        fill_w = int(width * (completed / total))
        self.canvas.coords(self.bar, 0, 0, fill_w, 24)
        self.canvas.coords(self.bar_text, 8, 12)
        self.canvas.itemconfig(self.bar_text, text=f"{pct}%")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.update_idletasks()

    def set_stat(self, key: str, value: int) -> None:
        label = key.capitalize()
        self.stats_vars[key].set(f"{label}: {value}")
        self.update_idletasks()

    def on_close(self) -> None:
        status = self.status_var.get().strip().lower()
        is_done = status in {"complete", "completed", "done", "finished"}
        if is_done:
            self.closed = True
            self.destroy()
            return
        if messagebox.askyesno(APP_TITLE, "Close the progress window? The download will keep running in the background."):
            self.closed = True
            self.destroy()

# -----------------------------
# Workflow helpers
# -----------------------------

def show_summary_confirm(selected_states: List[str], selected_zooms: List[int], total_bytes: int, total_tiles: int) -> bool:
    root = tk.Tk()
    root.configure(cursor="arrow")
    root.withdraw()
    state_summary = ", ".join(selected_states[:6])
    if len(selected_states) > 6:
        state_summary += f", ... ({len(selected_states)} total)"
    msg = (
        f"States:\n{state_summary}\n\n"
        f"Zooms:\n{', '.join(map(str, selected_zooms))}\n\n"
        f"Estimated size:\n{human_bytes(total_bytes)}\n\n"
        f"Estimated tiles:\n{total_tiles:,}\n\n"
        f"Continue to choose an output folder?"
    )
    answer = messagebox.askyesno(APP_TITLE, msg, parent=root)
    root.destroy()
    return bool(answer)


def ask_output_parent() -> str:
    try:
        if shutil.which("zenity"):
            result = subprocess.run(
                [
                    "zenity",
                    "--file-selection",
                    "--directory",
                    "--title=Select output parent folder",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return ""
    except Exception:
        pass

    root = tk.Tk()
    root.configure(cursor="arrow")
    root.withdraw()
    root.attributes("-topmost", True)
    root.update_idletasks()
    root.lift()
    try:
        folder = filedialog.askdirectory(
            title="Select output parent folder",
            parent=root,
        )
    finally:
        try:
            root.attributes("-topmost", False)
        except tk.TclError:
            pass
        root.destroy()
    return folder or ""


def fetch_tile(session: requests.Session, z: int, x: int, y: int, out_path: Path) -> str:
    if out_path.exists():
        return "existing"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = USGS_TILE_URL.format(z=z, x=x, y=y)
    try:
        with session.get(url, timeout=30, stream=True) as r:
            if r.status_code == 404:
                return "missing"
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
        return "downloaded"
    except Exception as e:
        log(f"ERROR downloading z{z}/{x}/{y}: {e}")
        try:
            if out_path.exists():
                out_path.unlink()
        except Exception:
            pass
        return "failed"


def build_tiles_for_state(rings: List[List[Tuple[float, float]]], zoom: int) -> List[Tuple[int, int]]:
    min_lon, min_lat, max_lon, max_lat = bbox_for_rings(rings)
    min_x, max_y = lonlat_to_tile(min_lon, min_lat, zoom)
    max_x, min_y = lonlat_to_tile(max_lon, max_lat, zoom)

    x_start, x_end = sorted((min_x, max_x))
    y_start, y_end = sorted((min_y, max_y))

    tiles = []
    for x in range(x_start, x_end + 1):
        for y in range(y_start, y_end + 1):
            lon, lat = tile_center_lonlat(x, y, zoom)
            if point_in_state(lon, lat, rings):
                tiles.append((x, y))
    return tiles


def run_download(selected_zooms: List[int], selected_states: List[str], mode: str, output_parent: Path, progress: ProgressWindow) -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="atak_states_"))
    stats = {"downloaded": 0, "existing": 0, "failed": 0, "missing": 0}

    try:
        progress.set_status("Downloading state boundaries...")
        geojson_path = download_state_geojson(temp_dir)
        progress.set_status("Loading state boundaries...")
        states = load_states(geojson_path)

        state_names = []
        for state_name in selected_states:
            if state_name not in states:
                raise RuntimeError(f"State not found in boundary file: {state_name}")
            if state_name == "District of Columbia":
                continue
            state_names.append(state_name)

        if not state_names:
            raise RuntimeError("No valid states selected.")

        output_root = output_parent / "Imagery"
        output_root.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        upload_dir = output_parent / f"ATAK_Upload_{date_str}"
        upload_dir.mkdir(parents=True, exist_ok=True)

        LAST_IMAGERY_ROOT_FILE.write_text(str(output_root), encoding="utf-8")
        log(f"Using output root: {output_root}")
        log(f"Using upload folder: {upload_dir}")
        log(f"Saved imagery path file: {LAST_IMAGERY_ROOT_FILE}")
        log(f"Selected states: {', '.join(state_names)}")

        plan: List[Tuple[str, int, int, int, Path]] = []
        progress.set_status("Scanning tile coverage...")
        for state_name in state_names:
            rings = states[state_name]
            for z in selected_zooms:
                progress.set_status(f"Scanning {state_name} zoom {z}...")
                tiles = build_tiles_for_state(rings, z)
                log(f"Planned {len(tiles)} tiles for {state_name}, zoom {z}")
                for x, y in tiles:
                    out_path = output_root / state_name / str(z) / str(x) / f"{y}.jpg"
                    plan.append((state_name, z, x, y, out_path))

        total = len(plan)
        log(f"Total tile candidates: {total}")
        progress.set_progress(0, total)
        progress.set_status("Starting download...")

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        completed = 0
        for state_name, z, x, y, out_path in plan:
            progress.set_status(f"Downloading {state_name} | zoom {z} | x={x} y={y}")
            result = fetch_tile(session, z, x, y, out_path)
            stats[result] += 1
            completed += 1
            progress.set_progress(completed, total)
            for key, value in stats.items():
                progress.set_stat(key, value)

            if completed % 25 == 0 or result in ("failed", "missing"):
                log(
                    f"Progress {completed}/{total} | "
                    f"downloaded={stats['downloaded']} existing={stats['existing']} "
                    f"missing={stats['missing']} failed={stats['failed']}"
                )

        progress.set_status("Complete")
        log("Download complete")
        log(f"Downloaded: {stats['downloaded']}")
        log(f"Existing: {stats['existing']}")
        log(f"Missing: {stats['missing']}")
        log(f"Failed: {stats['failed']}")
        progress.completion_message = "Download complete."

    except Exception as e:
        tb = traceback.format_exc()
        log(f"ERROR: {e}")
        log(tb)
        progress.error_message = f"Error:\n{e}\n\nLog file:\n{LOGGER.log_file}"
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            log(f"Deleted temp directory: {temp_dir}")
        except Exception as e:
            log(f"Warning: failed to delete temp directory: {e}")


def pump_gui_logs(window: ProgressWindow) -> None:
    try:
        while True:
            line = LOGGER.gui_queue.get_nowait()
            if not getattr(window, "closed", False):
                window.append_log(line)
    except queue.Empty:
        pass

    if not getattr(window, "closed", False):
        if getattr(window, "completion_message", None):
            msg = window.completion_message
            window.completion_message = None
            messagebox.showinfo(APP_TITLE, msg)
            try:
                window.closed = True
                window.destroy()

                if getattr(sys, "frozen", False):
                    if hasattr(sys, "_MEIPASS"):
                        os.environ["TCL_LIBRARY"] = str(Path(sys._MEIPASS) / "_tcl_data")
                        os.environ["TK_LIBRARY"] = str(Path(sys._MEIPASS) / "_tk_data")
                    import atak_imagery_sqlite_builder_finalbuild_win as sqlite_builder
                    sqlite_builder.main([])
                    os._exit(0)
                else:
                    next_script = Path(__file__).resolve().parent / "atak_imagery_sqlite_builder_finalbuild_win.py"
                    subprocess.Popen([sys.executable, str(next_script)])
                    os._exit(0)
            except Exception as exc:
                messagebox.showerror(APP_TITLE, f"Failed to launch SQLite builder:\n{exc}")
                sys.exit(1)

        if getattr(window, "error_message", None):
            msg = window.error_message
            window.error_message = None
            messagebox.showerror(APP_TITLE, msg)
            window.closed = True
            window.destroy()
            return

        window.after(150, pump_gui_logs, window)


def main() -> None:
    log(f"Log file: {LOGGER.log_file}")
    log(f"Bundled script directory: {BUNDLED_SCRIPT_DIR}")
    log(f"Runtime state directory: {RUNTIME_STATE_DIR}")
    log(f"Saved imagery path file: {LAST_IMAGERY_ROOT_FILE}")
    zoom_estimates = load_zoom_estimates()

    while True:
        selector = StateSelectionDialog()
        selector.mainloop()
        if not selector.result_states:
            log("Cancelled at state selection.")
            return

        zoom_dialog = ZoomDialog(selector.result_states, zoom_estimates)
        zoom_dialog.mainloop()

        if zoom_dialog.go_back:
            log("Back selected on zoom dialog.")
            continue

        selected_zooms = zoom_dialog.result
        if not selected_zooms:
            log("Cancelled at zoom selection.")
            return

        est_total_bytes = 0
        est_total_tiles = 0
        for z in selected_zooms:
            for state_name in selector.result_states:
                info = zoom_estimates.get(state_name, {}).get(str(z), {})
                est_total_bytes += int(info.get("estimated_bytes", 0))
                est_total_tiles += int(info.get("estimated_tiles", 0))

        if not show_summary_confirm(selector.result_states, selected_zooms, est_total_bytes, est_total_tiles):
            log("Summary declined. Returning to state selection.")
            continue

        output_folder = ask_output_parent()
        if not output_folder:
            log("Cancelled at output folder prompt.")
            return

        progress = ProgressWindow(LOGGER.log_file)
        pump_gui_logs(progress)

        worker = threading.Thread(
            target=run_download,
            args=(selected_zooms, selector.result_states, selector.result_mode, Path(output_folder), progress),
            daemon=True,
        )
        worker.start()
        progress.mainloop()
        return


if __name__ == "__main__":
    log("Starting Imagery Downloader")
    log(f"Python: {sys.version}")
    log(f"Working directory: {Path.cwd()}")
    log(f"Script directory: {Path(__file__).resolve().parent}")
    main()
