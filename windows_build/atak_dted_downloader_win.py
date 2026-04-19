#!/usr/bin/env python3
from __future__ import annotations

import queue
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

# -----------------------------
# CRITICAL FIX (same as others)
# -----------------------------
if getattr(sys, "frozen", False):
    RUNTIME_STATE_DIR = Path(sys.executable).resolve().parent
else:
    RUNTIME_STATE_DIR = Path(__file__).resolve().parent

LAST_IMAGERY_ROOT_FILE = RUNTIME_STATE_DIR / ".last_imagery_root.txt"
# -----------------------------


class Logger:
    def __init__(self) -> None:
        self.script_dir = Path(__file__).resolve().parent
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


LOGGER = Logger()


def log(msg: str) -> None:
    LOGGER.write(msg)


def main() -> None:
    log("Starting DTED downloader")

    if not LAST_IMAGERY_ROOT_FILE.exists():
        log("Missing saved imagery path file")
        return

    imagery_root = Path(LAST_IMAGERY_ROOT_FILE.read_text().strip())

    if not imagery_root.exists():
        log("Imagery path missing")
        return

    log(f"Using imagery root: {imagery_root}")
    log("DTED step placeholder complete")


if __name__ == "__main__":
    main()
