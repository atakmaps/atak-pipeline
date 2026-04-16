#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

APP_TITLE = "ATAK Pipeline"

SCRIPTS = [
    "atak_downloader_finalbuild.py",
    "atak_imagery_sqlite_builder_finalbuild.py",
    "atak_dted_downloader.py",
]


def get_script_dir() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "scripts"
    return Path(__file__).resolve().parent


def run_script(script_dir: Path, script_name: str) -> int:
    script_path = script_dir / script_name
    if not script_path.is_file():
        messagebox.showerror(APP_TITLE, f"Missing script:\n{script_path}")
        return 1

    try:
        result = subprocess.run([sys.executable, str(script_path)], check=False)
        return result.returncode
    except Exception as exc:
        messagebox.showerror(APP_TITLE, f"Failed to run:\n{script_name}\n\n{exc}")
        return 1


def main() -> int:
    root = tk.Tk()
    root.withdraw()

    script_dir = get_script_dir()

    for script_name in SCRIPTS:
        code = run_script(script_dir, script_name)
        if code != 0:
            messagebox.showerror(
                APP_TITLE,
                f"Pipeline stopped.\n\nScript failed:\n{script_name}\n\nExit code: {code}"
            )
            return code

    messagebox.showinfo(APP_TITLE, "Pipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
