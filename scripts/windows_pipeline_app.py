import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

APP_TITLE = "ATAK Pipeline"

STEPS = [
    ("Imagery Downloader", "atak_downloader_finalbuild.py"),
    ("SQLite Builder", "atak_imagery_sqlite_builder_finalbuild.py"),
    ("DTED Downloader", "atak_dted_downloader.py"),
]


def get_script_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "scripts"
    return Path(__file__).resolve().parent


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("560x260")
        self.root.resizable(False, False)

        self.status_var = tk.StringVar(value="Ready")
        self.step_var = tk.StringVar(value="Press Start to begin.")
        self.progress_var = tk.IntVar(value=0)

        frame = tk.Frame(root, padx=20, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=APP_TITLE, font=("Arial", 14, "bold")).pack(anchor="w", pady=(0, 12))
        tk.Label(frame, textvariable=self.status_var, font=("Arial", 11)).pack(anchor="w")
        tk.Label(frame, textvariable=self.step_var, fg="gray30").pack(anchor="w", pady=(6, 16))

        self.progress = ttk.Progressbar(frame, orient="horizontal", length=500, mode="determinate", maximum=100)
        self.progress.pack(anchor="w", pady=(0, 16))

        self.start_button = tk.Button(frame, text="Start Pipeline", width=18, command=self.start_pipeline)
        self.start_button.pack(anchor="w")

    def start_pipeline(self) -> None:
        self.start_button.config(state="disabled")
        threading.Thread(target=self.run_pipeline, daemon=True).start()

    def set_status(self, status: str, detail: str, progress: int) -> None:
        def apply():
            self.status_var.set(status)
            self.step_var.set(detail)
            self.progress["value"] = progress
        self.root.after(0, apply)

    def fail(self, msg: str) -> None:
        def apply():
            self.start_button.config(state="normal")
            messagebox.showerror(APP_TITLE, msg)
        self.root.after(0, apply)

    def done(self) -> None:
        def apply():
            self.status_var.set("Complete")
            self.step_var.set("Pipeline complete.")
            self.progress["value"] = 100
            messagebox.showinfo(APP_TITLE, "Pipeline complete.")
        self.root.after(0, apply)

    def run_pipeline(self) -> None:
        script_dir = get_script_dir()
        total = len(STEPS)

        for idx, (label, script_name) in enumerate(STEPS, start=1):
            script_path = script_dir / script_name
            if not script_path.is_file():
                self.fail(f"Missing script:\n{script_path}")
                return

            pct_start = int(((idx - 1) / total) * 100)
            self.set_status(f"Running {label}", f"Launching {script_name}", pct_start)

            try:
                result = subprocess.run([sys.executable, str(script_path)], check=False)
            except Exception as exc:
                self.fail(f"Failed to launch {script_name}\n\n{exc}")
                return

            if result.returncode != 0:
                self.fail(f"{label} failed.\n\nExit code: {result.returncode}")
                return

            pct_done = int((idx / total) * 100)
            self.set_status(f"Finished {label}", f"{script_name} completed successfully.", pct_done)

        self.done()


def main() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
