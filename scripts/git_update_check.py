"""
Optional git-based update check against origin/main (release line).

Skips entirely when not running from a git checkout (e.g. PyInstaller exe or release zip
without .git). Uses git fetch + compare; never runs in debug-only branches as the target —
updates always move the working tree to main and pull the latest release commits.

Restart after update uses os.execv with the same interpreter and argv.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional, Tuple


def read_version_file(repo_root: Path) -> str:
    vf = repo_root / "VERSION"
    if vf.is_file():
        line = vf.read_text(encoding="utf-8").strip().splitlines()
        return (line[0] if line else "").strip() or "unknown"
    return "unknown"


def find_repo_root(start: Path) -> Optional[Path]:
    p = start.resolve()
    for _ in range(16):
        if (p / ".git").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    return None


def _run_git(repo: Path, *args: str, timeout: float = 180) -> Tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "git not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "git timed out"
    except OSError as e:
        return 1, "", str(e)


class _GitUpdateState:
    __slots__ = ("done", "error", "update_available", "remote_version", "changelog", "behind")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.error: Optional[str] = None
        self.update_available = False
        self.remote_version = ""
        self.changelog: List[str] = []
        self.behind = 0


def _worker_fetch_and_compare(repo_root: Path, state: _GitUpdateState) -> None:
    try:
        code, _, err = _run_git(repo_root, "fetch", "origin", "main", timeout=180)
        if code != 0:
            state.error = err or "git fetch failed"
            return

        code, behind_txt, err = _run_git(repo_root, "rev-list", "--count", "HEAD..origin/main")
        if code != 0:
            state.error = err or "could not compare to origin/main"
            return
        try:
            n = int(behind_txt.strip())
        except ValueError:
            state.error = "unexpected git rev-list output"
            return
        if n <= 0:
            return

        state.update_available = True
        state.behind = n

        code, rv, _ = _run_git(repo_root, "show", "origin/main:VERSION", timeout=30)
        if code == 0 and rv.strip():
            state.remote_version = rv.strip().splitlines()[0].strip()
        else:
            code, tag, _ = _run_git(repo_root, "describe", "origin/main", "--tags", "--always", timeout=30)
            state.remote_version = tag.strip() if code == 0 else read_version_file(repo_root)

        code, log_out, _ = _run_git(
            repo_root,
            "log",
            "HEAD..origin/main",
            "--pretty=format:%s",
            "--no-decorate",
            "-n",
            "25",
            timeout=30,
        )
        state.changelog = [ln.strip() for ln in (log_out or "").splitlines() if ln.strip()]
    finally:
        state.done.set()


def _git_status_dirty(repo: Path) -> bool:
    code, out, _ = _run_git(repo, "status", "--porcelain", timeout=30)
    return code == 0 and bool(out.strip())


def _perform_update_and_restart(repo_root: Path, app_title: str) -> None:
    from tkinter import messagebox

    if _git_status_dirty(repo_root):
        code, _, err = _run_git(repo_root, "stash", "push", "-u", "-m", "atak-pipeline auto-update", timeout=120)
        if code != 0:
            messagebox.showerror(app_title, f"Could not stash local changes:\n{err or 'git stash failed'}")
            return

    code, _, err = _run_git(repo_root, "checkout", "main", timeout=60)
    if code != 0:
        code, _, err2 = _run_git(repo_root, "checkout", "-b", "main", "origin/main", timeout=60)
        if code != 0:
            messagebox.showerror(
                app_title,
                f"Could not checkout main:\n{err or err2 or 'git checkout failed'}",
            )
            return

    code, _, err = _run_git(repo_root, "pull", "origin", "main", "--ff-only", timeout=180)
    if code != 0:
        messagebox.showerror(
            app_title,
            f"Could not fast-forward main.\nResolve manually in:\n{repo_root}\n\n{err or 'git pull failed'}",
        )
        return

    messagebox.showinfo(app_title, "Update complete. The application will restart.")
    os.execv(sys.executable, [sys.executable, *sys.argv])


def run_startup_git_update_check(*, app_title: str, script_path: Path) -> None:
    """
    Call from main() before showing primary UI. May never return if user updates (os.execv).
    """
    if getattr(sys, "frozen", False):
        return

    repo_root = find_repo_root(script_path.parent)
    if repo_root is None:
        return

    state = _GitUpdateState()
    threading.Thread(target=_worker_fetch_and_compare, args=(repo_root, state), daemon=True).start()

    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.withdraw()

    progress: Optional[tk.Toplevel] = None
    progress_timer: Optional[str] = None

    def show_progress() -> None:
        nonlocal progress
        if state.done.is_set() or progress is not None:
            return
        progress = tk.Toplevel(root)
        progress.title(app_title)
        progress.resizable(False, False)
        progress.transient(root)
        frm = tk.Frame(progress, padx=16, pady=12)
        frm.pack()
        tk.Label(frm, text="Checking for updates…").pack(anchor="w")
        bar = ttk.Progressbar(frm, mode="indeterminate", length=280)
        bar.pack(pady=(8, 0))
        bar.start(12)
        progress.update_idletasks()

    progress_timer = root.after(2000, show_progress)

    def finish() -> None:
        nonlocal progress
        if progress_timer is not None:
            try:
                root.after_cancel(progress_timer)
            except tk.TclError:
                pass
        if progress is not None:
            try:
                progress.destroy()
            except tk.TclError:
                pass
            progress = None

        if state.error:
            root.destroy()
            return

        if not state.update_available:
            root.destroy()
            return

        local_v = read_version_file(repo_root)
        lines = state.changelog[:18]
        body = (
            f"Version {state.remote_version} is now available on main "
            f"(you are at {local_v}, {state.behind} new commit(s)).\n\n"
            f"Changes include:\n\n"
            + "\n".join(f"• {c}" for c in lines)
        )
        if len(state.changelog) > 18:
            body += "\n• …"
        body += (
            "\n\nUpdate now? Your repo will switch to branch main, fast-forward pull, "
            "and uncommitted changes will be stashed automatically if needed."
        )
        root.deiconify()
        root.update_idletasks()
        if not messagebox.askyesno(app_title, body, parent=root):
            root.destroy()
            return

        _perform_update_and_restart(repo_root, app_title)
        root.destroy()

    def poll() -> None:
        if state.done.is_set():
            finish()
        else:
            root.after(100, poll)

    root.after(50, poll)
    root.mainloop()
