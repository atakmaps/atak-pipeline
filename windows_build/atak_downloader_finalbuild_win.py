#!/usr/bin/env python3
"""
ATAK USGS Orthophoto Downloader (shared core, Windows)

**Two entry points:**

- **Standalone:** ``atak_downloader_finalbuild_win.py`` / launcher (full intro + Exit dialog).
- **After Device Installer:** ``atak_downloader_from_installer_win.py`` (skips USB/adb intro only; 
  same handoff dialog and SQLite builder as standalone).

- State selection first
- Zoom selection second
- Zoom screen: storage estimates, background USGS throughput probe, ETA vs selection
- Summary confirmation before output folder picker
- Progress bar during download
- Safe re-run: skips tiles that already exist

Output structure:
    <selected parent>/Imagery/State/zoom/x/y.jpg
"""

import importlib.util
import json
import math
import os
import queue
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import requests
import tkinter as tk
from tkinter import filedialog, messagebox

APP_TITLE = "ATAK Imagery Downloader"

LAUNCHED_FROM_DEVICE_INSTALLER_ENV = "ATAK_DOWNLOADER_LAUNCHED_FROM_DEVICE_INSTALLER"


def is_launched_from_device_installer() -> bool:
    return os.environ.get(LAUNCHED_FROM_DEVICE_INSTALLER_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


class DownloadCancelled(Exception):
    """Raised when the user stops the download from the progress window."""


USGS_TILE_URL = "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"
USER_AGENT = "ATAK-Ortho-Downloader/1.1"
# Parallel tile fetches (thread pool + throughput probe burst). Match Linux script.
MAX_DOWNLOAD_WORKERS = 24


def _shutdown_executor_pool(executor: ThreadPoolExecutor) -> None:
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)


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
STATE_GEOJSON_PATH = DATA_DIR / "us_states.geojson"
TILE_PLAN_DIR = DATA_DIR / "tile_plans" / "v1"
LAST_IMAGERY_ROOT_FILE = RUNTIME_STATE_DIR / ".last_imagery_root.txt"
LAST_IMAGERY_SESSION_STATES_FILE = RUNTIME_STATE_DIR / ".last_imagery_session_states.txt"


def _load_imagery_tile_selection():
    paths: List[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        paths.append(Path(sys._MEIPASS) / "scripts" / "imagery_tile_selection.py")
    here = Path(__file__).resolve().parent
    paths.extend([here / "imagery_tile_selection.py", here.parent / "scripts" / "imagery_tile_selection.py"])
    for path in paths:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("imagery_tile_selection", path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("imagery_tile_selection.py not found (bundle next to downloader or under scripts/)")


_its = _load_imagery_tile_selection()
lonlat_to_tile = _its.lonlat_to_tile
build_tiles_for_state = _its.build_tiles_for_state
STATE_BOUNDARY_BUFFER_MILES = _its.STATE_BOUNDARY_BUFFER_MILES

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
# Android / adb (aligned with atak_adb_deploy device step)
# -----------------------------


def _adb_executable() -> str:
    return shutil.which("adb") or "adb"


def _run_adb(args: List[str], serial: Optional[str] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = [_adb_executable()]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def adb_available() -> bool:
    try:
        r = subprocess.run(
            [_adb_executable(), "version"], capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


def adb_devices_raw() -> subprocess.CompletedProcess:
    _run_adb(["start-server"], serial=None, timeout=30)
    return _run_adb(["devices"], serial=None, timeout=30)


def parse_adb_devices_lines(stdout: str) -> Tuple[List[str], List[str]]:
    ready: List[str] = []
    diag: List[str] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        if line.startswith("*"):
            diag.append(line)
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if state == "device":
            ready.append(serial)
        else:
            diag.append(line)
    return ready, diag


def list_usb_devices() -> List[str]:
    r = adb_devices_raw()
    if r.returncode != 0:
        log(f"adb devices failed: {r.stderr or r.stdout}")
        return []
    ready, _diag = parse_adb_devices_lines(r.stdout)
    return ready


def adb_devices_human_summary() -> str:
    exe = _adb_executable()
    r = adb_devices_raw()
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    lines = [f"adb binary: {exe}", "", "$ adb devices", out or "(no stdout)"]
    if err:
        lines.extend(["", "stderr:", err])
    return "\n".join(lines)


def pick_adb_serial(devices: List[str]) -> Optional[str]:
    if not devices:
        return None
    if len(devices) == 1:
        return devices[0]
    pref = os.environ.get("ANDROID_SERIAL", "").strip()
    if pref and pref in devices:
        return pref
    return None


def ask_adb_serial_choice(parent: tk.Tk, devices: List[str]) -> Optional[str]:
    top = tk.Toplevel(parent)
    top.title("Select device")
    top.configure(cursor="arrow")
    top.transient(parent)
    top.grab_set()
    choice: List[Optional[str]] = [None]

    tk.Label(top, text="Multiple devices connected. Pick one:").pack(padx=12, pady=(12, 6))
    lb = tk.Listbox(top, height=min(len(devices), 8), width=40)
    for d in devices:
        lb.insert("end", d)
    lb.pack(padx=12, pady=6)
    lb.selection_set(0)

    def ok() -> None:
        sel = lb.curselection()
        if sel:
            choice[0] = devices[int(sel[0])]
        top.destroy()

    def cancel() -> None:
        top.destroy()

    bf = tk.Frame(top)
    bf.pack(pady=12)
    tk.Button(bf, text="OK", command=ok).pack(side="left", padx=6)
    tk.Button(bf, text="Cancel", command=cancel).pack(side="left", padx=6)
    parent.wait_window(top)
    return choice[0]


def check_device_ready_and_unlocked(serial: Optional[str]) -> Tuple[bool, str]:
    r = _run_adb(["shell", "getprop", "sys.boot_completed"], serial=serial, timeout=25)
    if r.returncode != 0:
        return False, (
            "Could not communicate with the device over adb.\n\n"
            "Check the USB cable, enable USB debugging, and accept the prompt on the phone."
        )
    if (r.stdout or "").strip() != "1":
        return False, "Wait until the device has finished booting to the home screen, then try again."

    r2 = _run_adb(["shell", "dumpsys", "window"], serial=serial, timeout=45)
    out = r2.stdout or ""
    if "mDreamingLockscreen=true" in out:
        return False, "Unlock your phone (dismiss the lock screen) and try again."
    return True, ""


def verify_adb_device_for_imagery_downloader(parent: tk.Tk) -> Tuple[bool, Optional[str], str]:
    if not adb_available():
        return False, None, (
            "adb was not found. Install Android platform tools (adb) and ensure it is on PATH."
        )

    devices = list_usb_devices()
    if not devices:
        detail = adb_devices_human_summary()
        if len(detail) > 2400:
            detail = detail[:2400] + "\n…"
        return False, None, (
            "No Android device in the *device* state (ready for adb).\n\n"
            "If the phone shows “unauthorized”, unlock it and accept the USB debugging "
            "prompt. If you see “no permissions”, install udev rules for adb.\n\n"
            f"{detail}"
        )

    serial = pick_adb_serial(devices)
    if serial is None and len(devices) > 1:
        serial = ask_adb_serial_choice(parent, devices)
    if not serial:
        return False, None, "No device was selected."

    ready, msg = check_device_ready_and_unlocked(serial)
    if not ready:
        return False, None, msg

    os.environ["ANDROID_SERIAL"] = serial
    return True, serial, ""


DOWNLOADER_INTRO_TEXT = (
    "This program will download imagery to your device. "
    "You must have ATAK installed on your device. "
    "If you do not have ATAK installed, exit this program and run the "
    "ATAK Device Installer application.\n\n"
    "\n\n"
    "1. On the phone, enable Developer options and USB debugging.\n"
    "2. Connect USB\n"
    "3. Select USB Mode, File Transfer\n\n"
    "Select Continue when your device is connected."
)


def show_downloader_intro_and_verify_device() -> bool:
    """ATAK + USB prerequisites, then adb device / unlock check. Return True to proceed."""
    root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("640x520")
    root.minsize(560, 420)
    root.configure(cursor="arrow")
    proceed = {"ok": False}

    tk.Label(root, text="Before you begin", font=("Arial", 12, "bold")).pack(anchor="w", padx=16, pady=(16, 6))
    tk.Label(root, text=DOWNLOADER_INTRO_TEXT, justify="left", wraplength=600).pack(anchor="w", padx=16, pady=(0, 8))

    status_var = tk.StringVar(value="")
    tk.Label(root, textvariable=status_var, fg="#333").pack(anchor="w", padx=16, pady=(4, 8))

    btn_row = tk.Frame(root)
    btn_row.pack(pady=12)

    def on_quit() -> None:
        proceed["ok"] = False
        root.destroy()

    btn_cont = tk.Button(btn_row, text="Continue", width=12)

    def on_continue() -> None:
        btn_cont.configure(state="disabled")
        status_var.set("Verifying device via adb…")
        root.update_idletasks()
        ok, _serial, err = verify_adb_device_for_imagery_downloader(root)
        btn_cont.configure(state="normal")
        status_var.set("")
        if not ok:
            messagebox.showwarning(APP_TITLE, err, parent=root)
            return
        proceed["ok"] = True
        root.destroy()

    btn_cont.configure(command=on_continue)
    btn_cont.pack(side="left", padx=6)
    tk.Button(btn_row, text="Quit", width=12, command=on_quit).pack(side="left", padx=6)

    root.protocol("WM_DELETE_WINDOW", on_quit)
    root.mainloop()
    return bool(proceed["ok"])


DOWNLOADER_NEXT_SQLITE_DIALOG_TEXT = (
    "Imagery successfully downloaded.\n\n"
    "Next will be to build the data for install on your device.\n\n"
    "Click Next to continue."
)


def show_downloader_session_exit_dialog(parent: tk.Tk, body: Optional[str] = None) -> None:
    """After imagery (and optional inline DTED), prompt user before launching the SQLite builder."""
    text = body if body is not None else DOWNLOADER_NEXT_SQLITE_DIALOG_TEXT
    dlg = tk.Toplevel(parent)
    dlg.title(APP_TITLE)
    dlg.configure(cursor="arrow")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(False, False)
    tk.Label(
        dlg,
        text=text,
        justify="center",
        wraplength=480,
    ).pack(padx=24, pady=(20, 12))

    def on_next() -> None:
        dlg.destroy()

    dlg.protocol("WM_DELETE_WINDOW", on_next)
    tk.Button(dlg, text="Next", width=12, command=on_next).pack(pady=(0, 20))
    parent.wait_window(dlg)


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


def human_throughput(bps: float) -> str:
    if bps <= 0:
        return "--"
    mb = bps / (1024 * 1024)
    if mb >= 0.05:
        return f"{mb:.1f} MB/s"
    kb = bps / 1024
    return f"{kb:.0f} KB/s"


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

def zoom_resolution_labels(z: int, latitude_deg: float = 39.0) -> str:
    equator_mpp = 156543.03392804097 / (2 ** z)
    local_mpp = equator_mpp * math.cos(math.radians(latitude_deg))
    local_ft = local_mpp * 3.28084
    return f"Zoom {z}  (~{equator_mpp:.2f} m/px equator, ~{local_ft:.1f} ft/px mid-US)"


def format_download_eta(seconds: float) -> str:
    if seconds <= 0 or math.isnan(seconds) or math.isinf(seconds):
        return "unknown"
    if seconds < 120:
        return f"about {max(1, int(seconds))} seconds"
    if seconds < 7200:
        return f"about {seconds / 60:.0f} minutes"
    hours = seconds / 3600.0
    if hours >= 72:
        return f"about {hours / 24:.1f} days"
    return f"about {hours:.1f} hours"


def measure_usgs_imagery_effective_bps() -> Optional[float]:
    """Sample aggregate bytes/sec with warm DNS/TLS and timed parallel bursts (matches worker count)."""
    z = 12
    lon0, lat0 = -98.35, 39.12
    x0, y0 = lonlat_to_tile(lon0, lat0, z)

    def urls_for_grid(ox: int, oy: int) -> List[str]:
        out: List[str] = []
        for i in range(MAX_DOWNLOAD_WORKERS):
            dx = i % 4
            dy = i // 4
            x, y = x0 + dx + ox, y0 + dy + oy
            out.append(USGS_TILE_URL.format(z=z, y=y, x=x))
        return out

    warm = requests.Session()
    warm.headers.update({"User-Agent": USER_AGENT})
    try:
        r0 = warm.get(USGS_TILE_URL.format(z=z, y=y0, x=x0), timeout=40)
        r0.raise_for_status()
        _ = r0.content
    except Exception as e:
        log(f"Imagery probe warm-up: {e}")
        return None

    def fetch_bytes(url: str) -> int:
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})
        try:
            rr = s.get(url, timeout=45)
            rr.raise_for_status()
            return len(rr.content)
        except Exception as e:
            log(f"Imagery throughput probe: {e}")
            return 0

    def burst_bps(urls: List[str]) -> Optional[float]:
        t0 = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as pool:
                parts = list(pool.map(fetch_bytes, urls))
        except Exception as e:
            log(f"Imagery throughput probe pool: {e}")
            return None
        elapsed = time.perf_counter() - t0
        total_b = sum(parts)
        ok = sum(1 for p in parts if p >= 512)
        if ok < max(4, MAX_DOWNLOAD_WORKERS // 2) or elapsed < 0.06 or total_b < 4096:
            return None
        return total_b / elapsed

    b1 = burst_bps(urls_for_grid(0, 0))
    b2 = burst_bps(urls_for_grid(5, 5))
    candidates = [b for b in (b1, b2) if b is not None]
    if not candidates:
        return None
    best = max(candidates)
    log(f"Imagery throughput probe: sampled aggregate {human_throughput(best)}")
    return best


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


def bundled_state_geojson_path() -> Path:
    """Census 2010 state boundaries shipped under data/ (no network fetch)."""
    if not STATE_GEOJSON_PATH.is_file():
        raise FileNotFoundError(
            f"Missing state boundaries file:\n{STATE_GEOJSON_PATH}\n\n"
            f"Ensure data/us_states.geojson is present next to zoom estimates."
        )
    log(f"Using bundled state boundaries: {STATE_GEOJSON_PATH}")
    return STATE_GEOJSON_PATH


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
        with_imagery = [s for s in selected if s != "District of Columbia"]
        if not with_imagery:
            messagebox.showwarning(
                APP_TITLE,
                "District of Columbia cannot be used alone for this download.\n\n"
                "USGS imagery here follows full state boundaries; Washington D.C. is omitted from that set.\n"
                "Select at least one state (e.g. Maryland or Delaware). Note: “District of Columbia” is "
                "listed right under Delaware.",
            )
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
        self.geometry("1040x780")
        self.resizable(False, False)
        self.configure(cursor="arrow")

        self.result: List[int] = []
        self.go_back = False
        self.zoom_total_bytes: Dict[int, int] = {}
        self.zoom_total_tiles: Dict[int, int] = {}
        self.vars: Dict[int, tk.BooleanVar] = {}
        self._probe_finished = False
        self._download_throughput_bps: Optional[float] = None

        frame = tk.Frame(self, padx=28, pady=20)
        frame.pack(fill="both", expand=True)

        note_wrap = 940

        tk.Label(
            frame,
            text="Selected states to be installed:",
            font=("Arial", 11, "bold"),
            anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        states_csv = ", ".join(sorted(selected_states))
        tk.Label(
            frame,
            text=states_csv,
            justify="left",
            wraplength=note_wrap,
            anchor="w",
            font=("Arial", 10),
            fg="gray30",
        ).pack(anchor="w", fill="x", pady=(0, 10))

        bg = frame.cget("bg")
        intro = tk.Text(
            frame,
            height=8,
            width=102,
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
        ).pack(anchor="w", fill="x", pady=(0, 4))

        self.download_time_var = tk.StringVar(
            value="Estimated time for download with your internet connection: measuring…"
        )
        tk.Label(
            frame,
            textvariable=self.download_time_var,
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
                wraplength=note_wrap,
                command=lambda zz=z: self._on_zoom_toggle(zz),
            )
            cb.pack(anchor="w", fill="x")

        btns = tk.Frame(frame)
        btns.pack(fill="x", pady=(16, 4), padx=(4, 4))
        tk.Button(btns, text="Back", width=12, command=self.back).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Select All", width=12, command=self.select_all).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Clear All", width=12, command=self.clear_all).pack(side="left", padx=(0, 6))
        tk.Button(btns, text="Cancel", width=12, command=self.cancel).pack(side="right", padx=(6, 0))
        tk.Button(btns, text="OK", width=12, command=self.submit).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))

        threading.Thread(target=self._throughput_probe_worker, daemon=True).start()
        self.update_size_label()

    def _throughput_probe_worker(self) -> None:
        try:
            bps = measure_usgs_imagery_effective_bps()
        except Exception as e:
            log(f"Imagery throughput probe failed: {e}")
            bps = None
        self.after(0, lambda b=bps: self._apply_probe_result(b))

    def _apply_probe_result(self, bps: Optional[float]) -> None:
        self._probe_finished = True
        self._download_throughput_bps = bps
        try:
            self.update_size_label()
        except tk.TclError:
            pass

    def select_all(self) -> None:
        for v in self.vars.values():
            v.set(True)
        self.update_size_label()

    def clear_all(self) -> None:
        for v in self.vars.values():
            v.set(False)
        self.update_size_label()

    def _on_zoom_toggle(self, z: int) -> None:
        """Checking a zoom level selects that level and every coarser level below it (10…z)."""
        if self.vars[z].get():
            for zz in range(10, z + 1):
                self.vars[zz].set(True)
        self.update_size_label()

    def update_size_label(self) -> None:
        selected = [z for z, var in self.vars.items() if var.get()]
        time_prefix = "Estimated time for download with your internet connection:"
        if not selected:
            self.temp_space_var.set(
                "Estimated temporary space needed for selected zooms: select at least one zoom"
            )
            self.device_var.set(
                "Estimated space to be installed on device: select at least one zoom"
            )
            if not self._probe_finished:
                self.download_time_var.set(f"{time_prefix} measuring connection to imagery server…")
            elif self._download_throughput_bps is None:
                self.download_time_var.set(
                    f"{time_prefix} could not measure speed (server unreachable or blocked)"
                )
            else:
                self.download_time_var.set(
                    f"{time_prefix} select zoom levels for an estimate."
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
        if not self._probe_finished:
            self.download_time_var.set(f"{time_prefix} measuring connection to imagery server…")
        elif self._download_throughput_bps is None or self._download_throughput_bps <= 0:
            self.download_time_var.set(
                f"{time_prefix} could not measure speed (server unreachable or blocked)"
            )
        else:
            eta_sec = total_bytes / self._download_throughput_bps
            self.download_time_var.set(
                f"{time_prefix} {format_download_eta(eta_sec)}"
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
    _PAUSED_STATUS_TEXT = "Paused — click Resume to continue"

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

        ctrl = tk.Frame(self, padx=10)
        ctrl.pack(fill="x", pady=(0, 4))
        self._ctl_lock = threading.Lock()
        self._paused = False
        self._cancel_requested = False
        self.user_cancelled = False
        self._last_activity_status = "Initializing..."
        self.btn_pause = tk.Button(ctrl, text="Pause", width=12, command=self._on_pause_toggle)
        self.btn_pause.pack(side="left", padx=(0, 8))
        tk.Button(ctrl, text="Cancel", width=12, command=self._on_cancel_download).pack(side="left")

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
        self.completion_log_summary = None
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

    def set_progress_fraction(self, frac: float, counter_detail: Optional[str] = None) -> None:
        frac = max(0.0, min(1.0, float(frac)))
        pct = int(frac * 100)
        if counter_detail is not None:
            self.counter_var.set(counter_detail)
        else:
            self.counter_var.set(f"{pct}%")
        self.update_idletasks()
        width = max(int(self.canvas.winfo_width()), 1)
        fill_w = int(width * frac)
        self.canvas.coords(self.bar, 0, 0, fill_w, 24)
        self.canvas.coords(self.bar_text, 8, 12)
        self.canvas.itemconfig(self.bar_text, text=f"{pct}%")

    def set_status(self, text: str) -> None:
        if text != self._PAUSED_STATUS_TEXT:
            self._last_activity_status = text
        self.status_var.set(text)
        self.update_idletasks()

    def set_stat(self, key: str, value: int) -> None:
        label = key.capitalize()
        self.stats_vars[key].set(f"{label}: {value}")
        self.update_idletasks()

    def _on_pause_toggle(self) -> None:
        with self._ctl_lock:
            self._paused = not self._paused
            now_paused = self._paused
            label = "Resume" if now_paused else "Pause"
        try:
            self.btn_pause.configure(text=label)
            if now_paused:
                self.set_status(self._PAUSED_STATUS_TEXT)
            else:
                self.set_status(self._last_activity_status)
        except tk.TclError:
            pass

    def _on_cancel_download(self) -> None:
        if not messagebox.askyesno(
            APP_TITLE,
            "Stop downloading and exit the program?",
            parent=self,
        ):
            return
        with self._ctl_lock:
            self._cancel_requested = True

    def wait_if_paused(self) -> None:
        while True:
            with self._ctl_lock:
                if self._cancel_requested:
                    raise DownloadCancelled()
                if not self._paused:
                    return
            time.sleep(0.05)

    def on_close(self) -> None:
        status = self.status_var.get().strip().lower()
        if status in {"complete", "completed", "done", "finished"}:
            self.closed = True
            self.destroy()
            return
        if status == "cancelled":
            self.closed = True
            self.destroy()
            return
        if messagebox.askyesno(
            APP_TITLE,
            "Stop downloading and exit the program?",
            parent=self,
        ):
            with self._ctl_lock:
                self._cancel_requested = True

# -----------------------------
# Workflow helpers
# -----------------------------

def show_summary_confirm(selected_states: List[str], selected_zooms: List[int], total_bytes: int, total_tiles: int) -> bool:
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
    if shutil.which("zenity"):
        try:
            r = subprocess.run(
                ["zenity", "--question", "--no-wrap", f"--title={APP_TITLE}", f"--text={msg}"],
                check=False,
            )
            return r.returncode == 0
        except OSError:
            pass

    root = tk.Tk()
    try:
        root.option_add("*cursor", "arrow")
    except tk.TclError:
        pass
    root.configure(cursor="arrow")
    root.withdraw()
    root.update_idletasks()
    try:
        root.update()
    except tk.TclError:
        pass
    answer = messagebox.askyesno(APP_TITLE, msg, parent=root)
    try:
        root.destroy()
    except tk.TclError:
        pass
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


DOWNLOAD_SESSION_LOCAL = threading.local()


def get_download_session() -> requests.Session:
    session = getattr(DOWNLOAD_SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        DOWNLOAD_SESSION_LOCAL.session = session
    return session


def fetch_tile(z: int, x: int, y: int, out_path: Path) -> Tuple[str, int]:
    if out_path.exists():
        return "existing", 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = USGS_TILE_URL.format(z=z, x=x, y=y)
    bytes_written = 0
    try:
        session = get_download_session()
        with session.get(url, timeout=30, stream=True) as r:
            if r.status_code == 404:
                return "missing", 0
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
                        bytes_written += len(chunk)
        return "downloaded", bytes_written
    except Exception as e:
        log(f"ERROR downloading z{z}/{x}/{y}: {e}")
        try:
            if out_path.exists():
                out_path.unlink()
        except Exception:
            pass
        return "failed", 0


def run_download(selected_zooms: List[int], selected_states: List[str], mode: str, output_parent: Path, progress: ProgressWindow) -> None:
    stats = {"downloaded": 0, "existing": 0, "failed": 0, "missing": 0}
    executor: Optional[ThreadPoolExecutor] = None

    try:
        log(f"run_download: states={selected_states!r} zooms={selected_zooms!r} mode={mode!r}")
        progress.wait_if_paused()
        progress.set_status("Loading state boundaries...")
        geojson_path = bundled_state_geojson_path()
        states = load_states(geojson_path)

        state_names = []
        for state_name in selected_states:
            if state_name not in states:
                raise RuntimeError(f"State not found in boundary file: {state_name}")
            if state_name == "District of Columbia":
                continue
            state_names.append(state_name)

        if not state_names:
            if not selected_states:
                raise RuntimeError(
                    "No valid states selected (empty list). "
                    "Try running the downloader again; if this repeats, keep the log file for support."
                )
            raise RuntimeError(
                "No states to download imagery for.\n\n"
                f"You selected: {', '.join(selected_states)}\n\n"
                "This tool skips District of Columbia: USGS state imagery uses full state shapes, "
                "and D.C. is not included as its own download region. "
                "Choose at least one state (for example Delaware or Maryland). "
                "D.C. is listed directly under Delaware in the list — easy to select by mistake."
            )

        output_root = output_parent / "Imagery"
        output_root.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now().strftime("%Y%m%d")
        upload_dir = output_parent / f"ATAK_Upload_{date_str}"
        upload_dir.mkdir(parents=True, exist_ok=True)

        LAST_IMAGERY_ROOT_FILE.write_text(str(output_root), encoding="utf-8")
        log(f"Using output root: {output_root}")
        log(f"Using upload folder: {upload_dir}")
        log(f"Saved imagery path file: {LAST_IMAGERY_ROOT_FILE}")
        log(
            f"Tile coverage: GeoJSON boundaries + {STATE_BOUNDARY_BUFFER_MILES:g} mi edge buffer "
            "(tile center inside polygon or within buffer of boundary)"
        )
        log(f"Selected states: {', '.join(state_names)}")

        plan: List[Tuple[str, int, int, int, Path]] = []
        progress.set_status("Scanning tile coverage...")
        for state_name in state_names:
            rings = states[state_name]
            for z in selected_zooms:
                progress.set_status(f"Scanning {state_name} zoom {z}...")
                tiles = build_tiles_for_state(
                    state_name,
                    rings,
                    z,
                    geojson_path=STATE_GEOJSON_PATH,
                    tile_plan_dir=TILE_PLAN_DIR,
                )
                log(f"Planned {len(tiles)} tiles for {state_name}, zoom {z}")
                for i, (x, y) in enumerate(tiles, start=1):
                    if i % 2048 == 0:
                        progress.wait_if_paused()
                    out_path = output_root / state_name / str(z) / str(x) / f"{y}.jpg"
                    plan.append((state_name, z, x, y, out_path))

        total = len(plan)
        log(f"Total tile candidates: {total}")
        progress.set_progress(0, total)
        progress.set_status("Starting download...")

        completed = 0
        downloaded_bytes = 0

        def download_one(tile: Tuple[str, int, int, int, Path]) -> Tuple[str, int, int, int, str, int]:
            state_name, z, x, y, out_path = tile
            result, bytes_written = fetch_tile(z, x, y, out_path)
            return state_name, z, x, y, result, bytes_written

        max_workers = max(1, min(MAX_DOWNLOAD_WORKERS, total if total > 0 else 1))
        progress.set_status(f"Starting download with {max_workers} workers...")

        future_to_tile = {}
        plan_iter = iter(plan)

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            for _ in range(max_workers):
                try:
                    tile = next(plan_iter)
                except StopIteration:
                    break
                future = executor.submit(download_one, tile)
                future_to_tile[future] = tile

            while future_to_tile:
                progress.wait_if_paused()
                done, _ = wait(list(future_to_tile.keys()), timeout=0.2, return_when=FIRST_COMPLETED)
                progress.wait_if_paused()
                if not done:
                    continue

                for future in done:
                    progress.wait_if_paused()
                    tile = future_to_tile.pop(future)
                    state_name, z, x, y, out_path = tile
                    progress.set_status(f"Downloading {state_name} | zoom {z} | x={x} y={y}")

                    try:
                        _, _, _, _, result, bytes_written = future.result()
                    except Exception as e:
                        log(f"ERROR downloading tile: {e}")
                        result, bytes_written = "failed", 0

                    stats[result] += 1
                    downloaded_bytes += bytes_written
                    completed += 1
                    progress.set_progress(completed, total)
                    for key, value in stats.items():
                        progress.set_stat(key, value)

                    if completed % 25 == 0 or result in ("failed", "missing"):
                        log(
                            f"Progress {completed}/{total} | "
                            f"downloaded={stats['downloaded']} existing={stats['existing']} "
                            f"missing={stats['missing']} failed={stats['failed']} "
                            f"bytes={downloaded_bytes}"
                        )

                    try:
                        next_tile = next(plan_iter)
                        next_future = executor.submit(download_one, next_tile)
                        future_to_tile[next_future] = next_tile
                    except StopIteration:
                        pass
        finally:
            if executor is not None:
                _shutdown_executor_pool(executor)
                executor = None

        log("Imagery tile download complete")
        log(f"Downloaded: {stats['downloaded']}")
        log(f"Existing: {stats['existing']}")
        log(f"Missing: {stats['missing']}")
        log(f"Failed: {stats['failed']}")

        try:
            LAST_IMAGERY_SESSION_STATES_FILE.write_text(
                "\n".join(sorted(state_names)) + "\n",
                encoding="utf-8",
            )
            log(
                f"Recorded states for next SQLite build: {', '.join(state_names)} "
                f"({LAST_IMAGERY_SESSION_STATES_FILE.name}). "
                "Older folders under Imagery/ will be skipped unless you delete that file."
            )
        except OSError as exc:
            log(f"WARNING: could not write session state list: {exc}")

        dted_note = ""
        try:
            import atak_dted_downloader_win as dted_mod

            dted_zip = dted_mod.run_dted_inline_for_states(
                state_names,
                upload_dir,
                log_sink=log,
                progress=progress,
            )
            if dted_zip is not None:
                dted_mod.mark_standalone_dted_skip()
                dted_note = f"\n\nDTED archive ready:\n{dted_zip.name}"
        except ImportError as exc:
            log(f"DTED: skipped (module not loadable: {exc}).")
        except DownloadCancelled:
            raise
        except Exception as exc:
            log(f"DTED: failed — {exc}")

        progress.set_status("Complete")
        progress.completion_log_summary = "Download complete." + dted_note
        progress.completion_message = DOWNLOADER_NEXT_SQLITE_DIALOG_TEXT + dted_note

    except DownloadCancelled:
        log("Download cancelled by user.")
        progress.user_cancelled = True
        progress.set_status("Cancelled")
    except Exception as e:
        tb = traceback.format_exc()
        log(f"ERROR: {e}")
        log(tb)
        progress.error_message = f"Error:\n{e}\n\nLog file:\n{LOGGER.log_file}"


def pump_gui_logs(window: ProgressWindow) -> None:
    try:
        while True:
            line = LOGGER.gui_queue.get_nowait()
            if not getattr(window, "closed", False):
                window.append_log(line)
    except queue.Empty:
        pass

    if not getattr(window, "closed", False):
        if getattr(window, "user_cancelled", False):
            window.closed = True
            try:
                window.destroy()
            except Exception:
                pass
            os._exit(0)

        if getattr(window, "completion_message", None):
            msg = window.completion_message
            window.completion_message = None
            summary = getattr(window, "completion_log_summary", None)
            if summary is not None:
                window.completion_log_summary = None
                log(summary.replace("\n\n", " | "))
            show_downloader_session_exit_dialog(window, body=msg)
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

    if is_launched_from_device_installer():
        log("Launched from Device Installer — skipping standalone USB/adb intro.")
    else:
        if not show_downloader_intro_and_verify_device():
            log("Exited at device verification prompt.")
            return

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

        zooms_arg = list(selected_zooms)
        states_arg = list(selector.result_states)
        worker = threading.Thread(
            target=run_download,
            args=(zooms_arg, states_arg, selector.result_mode, Path(output_folder), progress),
            daemon=True,
        )
        worker.start()
        progress.mainloop()
        return


if __name__ == "__main__":
    log("Starting ATAK Imagery Downloader")
    log(f"Python: {sys.version}")
    log(f"Working directory: {Path.cwd()}")
    log(f"Script directory: {Path(__file__).resolve().parent}")
    main()
