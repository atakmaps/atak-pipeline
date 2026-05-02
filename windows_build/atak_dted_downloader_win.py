#!/usr/bin/env python3
from __future__ import annotations

import queue
import re
import shutil
import sys
import os
import threading
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog


APP_TITLE = "ATAK DTED Downloader"
BASE_URL = "http://31.220.30.74/dted"
USER_AGENT = "ATAK-DTED-Downloader/1.0"
if getattr(sys, "frozen", False):
    RUNTIME_STATE_DIR = Path(sys.executable).resolve().parent
else:
    RUNTIME_STATE_DIR = Path(__file__).resolve().parent

LAST_IMAGERY_ROOT_FILE = RUNTIME_STATE_DIR / ".last_imagery_root.txt"


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
    "WI": "Wisconsin", "WY": "Wyoming",
}

CONTIGUOUS_48 = sorted(
    [name for name in STATE_ABBR_TO_NAME.values() if name not in ("Alaska", "Hawaii")]
)


class Logger:
    def __init__(self) -> None:
        self.script_dir = RUNTIME_STATE_DIR
        self.log_dir = self.script_dir / "logs"
        self.log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"atak_dted_downloader_{ts}.log"
        self._fh = open(self.log_file, "a", encoding="utf-8", buffering=1)
        self.gui_queue: "queue.Queue[str]" = queue.Queue()

    def write(self, message: str) -> None:
        if not message.endswith("\n"):
            message += "\n"
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
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


def clean_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned or "package"


def derive_package_folder_name(package_name: str) -> str:
    return f"atak_{clean_name(package_name)}"


def state_url(state_name: str) -> str:
    return f"{BASE_URL}/{state_name}/{state_name}.zip"


def ask_output_parent() -> str:
    root = tk.Tk()
    root.configure(cursor="arrow")
    root.withdraw()
    folder = filedialog.askdirectory(title="Select output parent folder")
    root.destroy()
    return folder or ""


def ask_package_name(default_name: str) -> str:
    root = tk.Tk()
    root.configure(cursor="arrow")
    root.withdraw()
    value = simpledialog.askstring(
        APP_TITLE,
        "Enter package name.\nThis creates an ATAK working folder named atak_<PackageName>.",
        initialvalue=default_name,
        parent=root,
    )
    root.destroy()
    return (value or "").strip()


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
            text="Select DTED package(s) to download:",
            font=("Arial", 11, "bold")
        ).pack(anchor="w", pady=(0, 8))

        note = (
            "Choose one or more specific states, or use the Contiguous 48 shortcut.\n"
            "The downloader will fetch state ZIPs, extract them, and build one final dted2.zip."
        )
        tk.Label(frame, text=note, justify="left").pack(anchor="w", pady=(0, 10))

        top_btns = tk.Frame(frame)
        top_btns.pack(fill="x", pady=(0, 8))

        tk.Button(top_btns, text="Contiguous 48", width=16, command=self.select_contiguous_48).pack(side="left", padx=(0, 6))
        tk.Button(top_btns, text="Select All", width=12, command=self.select_all).pack(side="left", padx=(0, 6))
        tk.Button(top_btns, text="Clear All", width=12, command=self.clear_all).pack(side="left", padx=(0, 6))

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

    def clear_all(self) -> None:
        self.result_mode = ""
        for var in self.vars.values():
            var.set(False)

    def select_contiguous_48(self) -> None:
        self.result_mode = "contiguous48"
        for state_name, var in self.vars.items():
            var.set(state_name in CONTIGUOUS_48)

    def submit(self) -> None:
        selected = sorted([state for state, var in self.vars.items() if var.get()])
        if not selected:
            messagebox.showwarning(APP_TITLE, "Select at least one state, or use Contiguous 48.")
            return
        self.result_states = selected
        if self.result_mode not in ("contiguous48", "all"):
            self.result_mode = "specific"
        self.destroy()

    def cancel(self) -> None:
        self.result_mode = ""
        self.result_states = []
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
        if messagebox.askyesno(APP_TITLE, "Close the progress window? The process will keep running in the background."):
            self.closed = True
            self.destroy()


def remote_file_size(session: requests.Session, url: str) -> int:
    try:
        resp = session.head(url, timeout=30, allow_redirects=True)
        if resp.status_code == 404:
            return -1
        resp.raise_for_status()
        value = resp.headers.get("Content-Length", "").strip()
        return int(value) if value.isdigit() else 0
    except requests.RequestException:
        return 0


def download_file(session: requests.Session, url: str, out_path: Path) -> str:
    size_hint = remote_file_size(session, url)
    if size_hint < 0:
        return "missing"

    if out_path.exists() and size_hint > 0 and out_path.stat().st_size == size_hint:
        return "existing"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".part")

    try:
        with session.get(url, timeout=300, stream=True) as r:
            if r.status_code == 404:
                return "missing"
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)
        tmp_path.replace(out_path)
        return "downloaded"
    except Exception as exc:
        log(f"ERROR downloading {url}: {exc}")
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return "failed"


def extract_state_zip(zip_path: Path, extract_root: Path) -> None:
    state_name = zip_path.stem
    state_extract_dir = extract_root / state_name
    if state_extract_dir.exists():
        shutil.rmtree(state_extract_dir)
    state_extract_dir.mkdir(parents=True, exist_ok=True)

    log(f"Extracting {zip_path.name} -> {state_extract_dir}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(state_extract_dir)


def build_final_dted_zip(extract_root: Path, final_zip_path: Path) -> None:
    if final_zip_path.exists():
        final_zip_path.unlink()

    log(f"Building final ATAK zip: {final_zip_path}")

    with zipfile.ZipFile(final_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
        for state_dir in sorted(extract_root.iterdir(), key=lambda p: p.name.lower()):
            if not state_dir.is_dir():
                continue

            for item in sorted(state_dir.rglob("*")):
                if not item.is_file():
                    continue
                arcname = item.relative_to(state_dir)
                zf.write(item, arcname.as_posix())
                log(f"ADD {arcname.as_posix()}")

    log(f"Final zip ready: {final_zip_path}")


def run_download(selected_states: List[str], mode: str, output_parent: Path, package_name: str, progress: ProgressWindow) -> None:
    stats = {"downloaded": 0, "existing": 0, "failed": 0, "missing": 0}

    try:
        from datetime import datetime
        import tempfile

        date_str = datetime.now().strftime("%Y%m%d")
        ts = datetime.now().strftime("%H%M%S")

        upload_dir = output_parent / f"ATAK_Upload_{date_str}"
        upload_dir.mkdir(parents=True, exist_ok=True)

        temp_root = Path(tempfile.mkdtemp(prefix="atak_dted_"))
        downloads_dir = temp_root / "_state_zips"
        extract_root = temp_root / "_extracted_states"
        final_zip_path = upload_dir / f"dted2_{ts}.zip"

        downloads_dir.mkdir(parents=True, exist_ok=True)
        extract_root.mkdir(parents=True, exist_ok=True)

        log(f"Using upload folder: {upload_dir}")
        log(f"Using temp work folder: {temp_root}")
        log(f"Server base URL: {BASE_URL}")

        plan = []
        for state_name in selected_states:
            url = state_url(state_name)
            out_path = downloads_dir / state_name / f"{state_name}.zip"
            plan.append((state_name, url, out_path))

        total = len(plan)
        progress.set_progress(0, total)
        progress.set_status("Downloading state ZIPs...")

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        completed = 0
        for state_name, url, out_path in plan:
            progress.set_status(f"Downloading {state_name}")
            log(f"Requesting: {url}")
            result = download_file(session, url, out_path)
            stats[result] += 1
            completed += 1

            progress.set_progress(completed, total)
            for key, value in stats.items():
                progress.set_stat(key, value)

            log(f"{state_name}: {result} -> {out_path} | progress {completed}/{total}")

        if stats["failed"] > 0:
            raise RuntimeError(
                f"Download incomplete. failed={stats['failed']} missing={stats['missing']}."
            )

        if stats["missing"] > 0:
            log(f"WARNING: continuing with missing tiles: {stats['missing']}")

        progress.set_status("Extracting state ZIPs...")
        extracted_any = False
        for state_name, _, out_path in plan:
            if not out_path.exists():
                log(f"WARNING: skipping missing zip during extraction: {out_path}")
                continue
            extract_state_zip(out_path, extract_root)
            extracted_any = True

        if not extracted_any:
            progress.completion_message = "No DTED packages were available for the selected state(s)."
            return

        progress.set_status("Building final dted2.zip...")
        build_final_dted_zip(extract_root, final_zip_path)

        progress.set_status("Cleaning temporary files...")
        shutil.rmtree(downloads_dir, ignore_errors=True)
        shutil.rmtree(extract_root, ignore_errors=True)

        progress.set_status("Complete")
        log("DTED download complete")
        log(f"Mode: {mode}")
        log(f"Selected states: {', '.join(selected_states)}")
        log(f"Upload folder: {upload_dir}")
        log(f"Final ATAK zip: {final_zip_path}")
        log(f"Downloaded: {stats['downloaded']}")
        log(f"Existing: {stats['existing']}")
        log(f"Missing: {stats['missing']}")
        log(f"Failed: {stats['failed']}")

        progress.completion_message = "DTED build complete."
        try:
            LOGGER.close()
        except Exception:
            pass
        return

    except Exception as exc:
        tb = traceback.format_exc()
        log(f"ERROR: {exc}")
        log(tb)
        progress.error_message = f"Error:\n{exc}\n\nLog file:\n{LOGGER.log_file}"


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

            upload_dir = None
            try:
                if LAST_IMAGERY_ROOT_FILE.exists():
                    imagery_root = Path(LAST_IMAGERY_ROOT_FILE.read_text(encoding="utf-8").strip())
                    if imagery_root.is_dir():
                        from datetime import datetime
                        date_str = datetime.now().strftime("%Y%m%d")
                        upload_dir = imagery_root.parent / f"ATAK_Upload_{date_str}"

                        cleanup = messagebox.askyesno(
                            APP_TITLE,
                            "DTED build succeeded.\n\n"
                            "ATAK only needs the final SQLite and DTED outputs.\n\n"
                            f"Delete raw downloaded imagery now?\n\n{imagery_root}"
                        )
                        if cleanup:
                            import shutil
                            shutil.rmtree(imagery_root)
                            log(f"Deleted raw imagery folder: {imagery_root}")
                            try:
                                LAST_IMAGERY_ROOT_FILE.unlink()
                                log(f"Deleted saved imagery path file: {LAST_IMAGERY_ROOT_FILE}")
                            except Exception as cleanup_exc:
                                log(f"Warning: saved imagery path file removal failed: {cleanup_exc}")
                        else:
                            log(f"Raw imagery retained: {imagery_root}")
            except Exception as cleanup_exc:
                log(f"Warning: raw imagery cleanup failed: {cleanup_exc}")
                try:
                    messagebox.showwarning(APP_TITLE, f"Raw imagery cleanup failed:\n{cleanup_exc}")
                except Exception:
                    pass

            try:

                messagebox.showinfo(
                    APP_TITLE,
                    "Your ATAK imagery and DTED build is complete.\n\n"
                    "Please copy the .sql and DTED files into your /Downloads folder on your Android device."
                )

                if upload_dir and upload_dir.exists():
                    import subprocess, sys, os
                    try:
                        if sys.platform.startswith("linux"):
                            subprocess.Popen(["xdg-open", str(upload_dir)])
                        elif sys.platform.startswith("win"):
                            os.startfile(str(upload_dir))
                        elif sys.platform == "darwin":
                            subprocess.Popen(["open", str(upload_dir)])
                    except Exception as open_exc:
                        log(f"WARNING: failed to open upload folder: {open_exc}")
            except Exception:
                pass

            window.closed = True
            try:
                window.quit()
                window.destroy()
            except Exception:
                pass
            return

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
    log(f"Server base URL: {BASE_URL}")

    selector = StateSelectionDialog()
    selector.mainloop()

    if not selector.result_states:
        log("Cancelled at state selection.")
        return

    if selector.result_mode == "contiguous48":
        default_package_name = "Contiguous_48"
    elif selector.result_mode == "all":
        default_package_name = "All_States"
    elif len(selector.result_states) == 1:
        default_package_name = selector.result_states[0]
    else:
        default_package_name = "Selected_States"

    if not LAST_IMAGERY_ROOT_FILE.exists():
        log(f"Missing saved imagery path file: {LAST_IMAGERY_ROOT_FILE}")
        return

    imagery_root = Path(LAST_IMAGERY_ROOT_FILE.read_text(encoding="utf-8").strip())
    if not imagery_root.is_dir():
        log(f"Saved imagery folder not found: {imagery_root}")
        return

    output_folder = str(imagery_root.parent)

    package_name = "DTED"
    log(f"Using imagery parent folder for DTED output: {output_folder}")

    progress = ProgressWindow(LOGGER.log_file)
    pump_gui_logs(progress)

    worker = threading.Thread(
        target=run_download,
        args=(selector.result_states, selector.result_mode, Path(output_folder), package_name, progress),
        daemon=True,
    )
    worker.start()
    progress.mainloop()


if __name__ == "__main__":
    log("Starting ATAK DTED Downloader")
    log(f"Python: {sys.version}")
    log(f"Working directory: {Path.cwd()}")
    log(f"Script directory: {Path(__file__).resolve().parent}")
    main()
