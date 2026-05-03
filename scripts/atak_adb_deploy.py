#!/usr/bin/env python3
"""
ATAK + plugin install over ADB, then launch the normal imagery pipeline.

Configuration (environment variables):

  ATAK_DEPLOY_MANIFEST_URL — required for USB install. Set it in deploy.env at
    the project root (uncommented KEY=value lines) or in the process environment.
    The installer copies deploy.env.example to deploy.env on first run.
    Manifest JSON shape, for example:
      {
        "atak_version": "5.2.0",
        "atak_apk_url": "/releases/atak.apk",
        "plugin_apk_url": "/releases/plugin.apk"
      }
    Relative URLs are resolved against the manifest URL. You may omit
    plugin_apk_url when using ATAK_PLUGIN_GITHUB_REPO or other env sources.

  ATAK_DEPLOY_REPORT_URL — optional. Receives POST JSON when installs progress:
      After ATAK install (phase "atak_installed"):
        atak_version, android_serial, plugin_source (empty string), phase.
      After plugin install (phase "complete"):
        atak_version, plugin_source, android_serial, phase.
    If a POST fails, the error is logged and the wizard continues unless
    ATAK_DEPLOY_REPORT_STRICT=1 is set (then the step aborts with an error dialog).

  ATAK_DEPLOY_API_TOKEN — optional. Sent as Authorization: Bearer when posting reports.

  ATAK_PLUGIN_APK — optional explicit local path (overrides all other plugin sources).

  ATAK_PLUGIN_GITHUB_REPO — recommended for production: "owner/repo". Downloads the
    chosen .apk from the latest GitHub release (official signed release asset when
    present; debug-named assets are skipped if a non-debug .apk exists on the same
    release). Uses the API; optional GITHUB_TOKEN or ATAK_GITHUB_TOKEN.

  ATAK_PLUGIN_REPO — optional root directory; the newest *.apk under it (may be a
    debug build—prefer GitHub for installable release APKs).

  ATAK_PLUGIN_APK_URL — optional HTTP(S) URL or path relative to the manifest URL.

  Alternatively, add optional plugin_apk_url to the manifest JSON (lowest priority
  among network/manifest sources after the above).

  ATAK_PACKAGE_NAME — ATAK applicationId to install/launch (default
    com.atakmap.app.civ).

Server operators can host the manifest next to the ATAK APK and update
atak_version / atak_apk_url whenever you publish a new build; the POST to
ATAK_DEPLOY_REPORT_URL records what was installed on each device.

If adb reports INSTALL_FAILED_VERSION_DOWNGRADE (APK versionCode lower than the
  installed app), the installer retries with ``adb install --allow-downgrade -r``.
  If the phone's package manager does not support that flag (IllegalArgumentException /
  Unknown option), it retries again with the legacy ``-d`` flag (``adb install -d -r``).

DEBUG — REMOVE BEFORE RELEASE (do not ship; remove before pushing a release):
  DeployWizard shows one temporary “Skip (debug)” button on the Installing ATAK and
  Installing plugin steps (same widget position; command switches) to bypass those APK installs
  while testing the rest of the wizard (_on_debug_skip_atak_install, _on_debug_skip_plugin_install).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk
except Exception:  # pragma: no cover
    tk = None
    messagebox = None
    scrolledtext = None
    ttk = None

APP_TITLE = "ATAK Device Installer"
DEFAULT_ATAK_PACKAGE = "com.atakmap.app.civ"

# After ATAK APK is installed: show this while the user completes first-run on device.
ATAK_POST_INSTALL_SETUP_INSTRUCTIONS = (
    "Follow setup prompts\n\n"
    "1. Agree to the EULA\n\n"
    "2. Follow the prompts. For each question select “Allow”, “Allow while using the app”, "
    "and select “Allow All” if it is displayed.\n\n"
    "3. Select “I understand” when it asks for background location\n\n"
    "4. Select “Ok” for Android 11+ Warning\n\n"
    "5. Select “I Understand” for required missing permissions\n\n"
    "6. Settings window: Select “Permissions”, then “Location”, then “Allow all the time”\n\n"
    "7. Select the back arrow until you return to ATAK\n\n"
    "8. Select “I understand” for file system access\n\n"
    "9. Settings window: Turn on “Allow access to manage all files”\n\n"
    "10. Select the back arrow\n\n"
    "11. Select “Done” on the TAK Device Setup screen\n\n"
    "12. Select “Do not show this hint again” and OK\n\n"
    "13. Select “Allow” to allow to run in background\n\n"
    "14. Select “Continue” on this window. Allow ATAK to install the plugin.\n\n"
    "Leave ATAK open on the main map.\n\n"
    "When setup is complete, select Continue."
)

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    SCRIPT_DIR = Path(sys._MEIPASS) / "scripts"
else:
    SCRIPT_DIR = Path(__file__).resolve().parent

DOWNLOADER = SCRIPT_DIR / "atak_downloader_finalbuild.py"
USER_AGENT = "ATAK-Pipeline-Deploy/1.0"
PROJECT_ROOT = SCRIPT_DIR.parent
DEPLOY_ENV_PATH = PROJECT_ROOT / "deploy.env"


def load_deploy_env_file() -> None:
    if not DEPLOY_ENV_PATH.is_file():
        return
    try:
        raw = DEPLOY_ENV_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if not key or not val:
            continue
        if not os.environ.get(key, "").strip():
            os.environ[key] = val


def ensure_gui_path_for_adb() -> None:
    """Desktop .desktop launches often have a short PATH; match common dev locations."""
    home = Path.home()
    extras = [
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        str(home / "Android/Sdk/platform-tools"),
        str(home / "Android/Sdk/cmdline-tools/latest/bin"),
    ]
    path = os.environ.get("PATH", "")
    parts = [p for p in path.split(os.pathsep) if p]
    merged = path
    for e in reversed(extras):
        if e not in parts and Path(e).is_dir():
            merged = e + os.pathsep + merged
            parts.insert(0, e)
    os.environ["PATH"] = merged


def log(msg: str) -> None:
    line = msg if msg.endswith("\n") else msg + "\n"
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass


def env_optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def atak_package_name() -> str:
    return env_optional("ATAK_PACKAGE_NAME", DEFAULT_ATAK_PACKAGE)


def adb_executable() -> str:
    return shutil.which("adb") or "adb"


def run_adb(args: List[str], serial: Optional[str] = None, timeout: int = 120) -> subprocess.CompletedProcess:
    cmd = [adb_executable()]
    if serial:
        cmd += ["-s", serial]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def adb_available() -> bool:
    try:
        r = subprocess.run(
            [adb_executable(), "version"], capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0
    except Exception:
        return False


def adb_devices_raw() -> subprocess.CompletedProcess:
    """Run plain ``adb devices`` (no ``-l``) for stable, whitespace-tolerant parsing."""
    run_adb(["start-server"], serial=None, timeout=30)
    return run_adb(["devices"], serial=None, timeout=30)


def parse_adb_devices_lines(stdout: str) -> Tuple[List[str], List[str]]:
    """Return (serials in *device* state, diagnostic lines for any other row)."""
    ready: List[str] = []
    diag: List[str] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        if line.startswith("*"):  # e.g. daemon messages
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
    """For error dialogs: adb path + full ``adb devices`` output."""
    exe = adb_executable()
    r = adb_devices_raw()
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    lines = [f"adb binary: {exe}", "", "$ adb devices", out or "(no stdout)"]
    if err:
        lines.extend(["", "stderr:", err])
    return "\n".join(lines)


def resolve_url(manifest_url: str, maybe_relative: str) -> str:
    return urllib.parse.urljoin(manifest_url, maybe_relative)


def fetch_manifest(url: str) -> Dict[str, Any]:
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")
    return data


def github_release_api_headers() -> Dict[str, str]:
    h = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = env_optional("GITHUB_TOKEN") or env_optional("ATAK_GITHUB_TOKEN")
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def github_latest_release_apk_browser_url(owner_repo: str) -> str:
    """Return browser_download_url for the preferred release .apk on the repo's latest GitHub release.

    Prefers non-debug assets, then names containing both *plugin* and *release*, then *release*.
    """
    slug = owner_repo.strip().strip("/")
    parts = [p for p in slug.split("/") if p]
    if len(parts) != 2:
        raise ValueError(
            f"ATAK_PLUGIN_GITHUB_REPO must be owner/repo (e.g. atakmaps/BTECH-Relay), got {owner_repo!r}"
        )
    owner, repo = parts[0], parts[1]
    api = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    r = requests.get(api, headers=github_release_api_headers(), timeout=60)
    r.raise_for_status()
    data = r.json()
    assets = data.get("assets") or []
    apk_assets = [a for a in assets if str(a.get("name", "")).lower().endswith(".apk")]
    if not apk_assets:
        tag = data.get("tag_name", "?")
        raise RuntimeError(
            f"Latest GitHub release {owner}/{repo} ({tag}) has no .apk assets."
        )

    def name_lower(i: int) -> str:
        return str(apk_assets[i].get("name", "")).lower()

    # Drop debug-named APKs when a release-named alternative exists on the same release.
    non_debug_idx = [i for i in range(len(apk_assets)) if "debug" not in name_lower(i)]
    pool_idx = non_debug_idx if non_debug_idx else list(range(len(apk_assets)))

    def prefer() -> int:
        for i in pool_idx:
            n = name_lower(i)
            if "plugin" in n and "release" in n:
                return i
        for i in pool_idx:
            n = name_lower(i)
            if "release" in n:
                return i
        return pool_idx[0]

    chosen = apk_assets[prefer()]
    return str(chosen["browser_download_url"])


def download_file(url: str, dest: Path, status_cb=None, timeout: int = 600) -> None:
    headers = {"User-Agent": USER_AGENT}
    with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if status_cb and total:
                    status_cb(downloaded, total)


def install_apk(serial: str, apk_path: Path, status_cb=None) -> None:
    """Install APK with optional downgrade retries (newer and older Android pm installs)."""
    name = apk_path.name
    if status_cb:
        status_cb(f"Installing {name}…")
    r = run_adb(["install", "-r", str(apk_path)], serial=serial, timeout=600)
    combined = (r.stderr or "") + (r.stdout or "")

    if r.returncode != 0 and "INSTALL_FAILED_VERSION_DOWNGRADE" in combined:
        log("adb install: INSTALL_FAILED_VERSION_DOWNGRADE; retrying with --allow-downgrade")
        if status_cb:
            status_cb(f"Installing {name} (allow downgrade)…")
        r = run_adb(
            ["install", "--allow-downgrade", "-r", str(apk_path)],
            serial=serial,
            timeout=600,
        )
        combined = (r.stderr or "") + (r.stdout or "")
        if r.returncode != 0 and _device_rejects_allow_downgrade_flag(combined):
            log("adb install: device pm has no --allow-downgrade; retrying with -d")
            if status_cb:
                status_cb(f"Installing {name} (allow downgrade, -d)…")
            r = run_adb(["install", "-d", "-r", str(apk_path)], serial=serial, timeout=600)

    if r.returncode != 0:
        raise RuntimeError(f"adb install failed:\n{(r.stderr or r.stdout).strip()}")


def _device_rejects_allow_downgrade_flag(combined: str) -> bool:
    """True if device's ``pm install`` failed because ``--allow-downgrade`` is unsupported."""
    if not combined:
        return False
    lower = combined.lower()
    if "unknown option" in lower and "allow-downgrade" in lower:
        return True
    if "illegalargumentexception" in lower and "allow-downgrade" in lower:
        return True
    return False


def launch_atak(serial: str) -> None:
    pkg = atak_package_name()
    r = run_adb(
        ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
        serial=serial,
        timeout=60,
    )
    if r.returncode != 0:
        log(f"monkey launch returned {r.returncode}: {r.stderr}")


def post_report(
    report_url: str,
    token: Optional[str],
    atak_version: str,
    plugin_source: str,
    android_serial: str,
    phase: str,
) -> None:
    payload = {
        "atak_version": atak_version,
        "plugin_source": plugin_source,
        "android_serial": android_serial,
        "phase": phase,
    }
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(report_url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()


def safe_post_report(
    report_url: str,
    token: Optional[str],
    atak_version: str,
    plugin_source: str,
    android_serial: str,
    phase: str,
) -> None:
    strict = env_optional("ATAK_DEPLOY_REPORT_STRICT") == "1"
    try:
        post_report(report_url, token, atak_version, plugin_source, android_serial, phase)
    except requests.RequestException as exc:
        log(f"ATAK_DEPLOY_REPORT_URL POST failed ({phase}): {exc}")
        if strict:
            raise


def resolve_plugin_apk(manifest: Dict[str, Any], manifest_url: str) -> Tuple[Path, str, bool]:
    """
    Returns (path to apk, description for report, whether temp file should be deleted).

    Resolution order:
      1. ATAK_PLUGIN_APK — explicit file
      2. ATAK_PLUGIN_GITHUB_REPO — latest GitHub release (preferred release APK)
      3. ATAK_PLUGIN_REPO — newest .apk under directory
      4. ATAK_PLUGIN_APK_URL — download
      5. plugin_apk_url from manifest
    """
    env_apk = env_optional("ATAK_PLUGIN_APK")
    if env_apk:
        p = Path(env_apk).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"ATAK_PLUGIN_APK is not a file: {p}")
        return p, str(p), False

    gh = env_optional("ATAK_PLUGIN_GITHUB_REPO")
    if gh:
        full = github_latest_release_apk_browser_url(gh)
        fd, tmp = tempfile.mkstemp(suffix=".apk")
        os.close(fd)
        tmp_path = Path(tmp)
        download_file(full, tmp_path)
        return tmp_path, full, True

    repo = env_optional("ATAK_PLUGIN_REPO")
    if repo:
        root = Path(repo).expanduser()
        apks = [x for x in root.rglob("*.apk") if x.is_file()]
        if not apks:
            raise FileNotFoundError(f"No .apk files under ATAK_PLUGIN_REPO: {root}")
        newest = max(apks, key=lambda x: x.stat().st_mtime)
        return newest, str(newest), False

    plugin_env_url = env_optional("ATAK_PLUGIN_APK_URL")
    if plugin_env_url:
        if plugin_env_url.startswith("http://") or plugin_env_url.startswith("https://"):
            full = plugin_env_url
        else:
            full = resolve_url(manifest_url, plugin_env_url)
        fd, tmp = tempfile.mkstemp(suffix=".apk")
        os.close(fd)
        tmp_path = Path(tmp)
        download_file(full, tmp_path)
        return tmp_path, full, True

    url = manifest.get("plugin_apk_url")
    if not url:
        raise RuntimeError(
            "No plugin APK source: set ATAK_PLUGIN_GITHUB_REPO (recommended), ATAK_PLUGIN_APK_URL, "
            "ATAK_PLUGIN_APK, ATAK_PLUGIN_REPO, or plugin_apk_url in the manifest."
        )
    full = resolve_url(manifest_url, str(url))
    fd, tmp = tempfile.mkstemp(suffix=".apk")
    os.close(fd)
    tmp_path = Path(tmp)
    download_file(full, tmp_path)
    return tmp_path, full, True


def resolve_atak_apk(manifest: Dict[str, Any], manifest_url: str) -> Tuple[Path, str, bool]:
    ver = manifest.get("atak_version")
    url = manifest.get("atak_apk_url")
    if not ver or not url:
        raise RuntimeError("Manifest must include atak_version and atak_apk_url")
    full = resolve_url(manifest_url, str(url))
    fd, tmp = tempfile.mkstemp(suffix=".apk")
    os.close(fd)
    tmp_path = Path(tmp)
    download_file(full, tmp_path)
    return tmp_path, str(ver), True


def pick_serial(devices: List[str]) -> Optional[str]:
    if not devices:
        return None
    if len(devices) == 1:
        return devices[0]
    pref = env_optional("ANDROID_SERIAL")
    if pref and pref in devices:
        return pref
    return None


class DeployWizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("560x520")
        self.minsize(520, 420)
        self.configure(cursor="arrow")
        self.selected_serial: Optional[str] = None
        self.manifest_url = env_optional("ATAK_DEPLOY_MANIFEST_URL")
        self.report_url = env_optional("ATAK_DEPLOY_REPORT_URL")
        self._atak_apk_temp: Optional[Path] = None
        self._plugin_apk_temp: Optional[Path] = None
        self._manifest_cache: Optional[Dict[str, Any]] = None
        self._atak_version_value = ""
        self._plugin_report_label = ""
        self._debug_skip_atak_pending = False
        self._debug_skip_plugin_pending = False

        outer = tk.Frame(self, padx=16, pady=16)
        outer.configure(cursor="arrow")
        outer.pack(fill="both", expand=True)

        self.step_label = tk.Label(outer, text="", font=("Arial", 12, "bold"), anchor="w", justify="left")
        self.step_label.pack(fill="x", pady=(0, 8))

        self.body = tk.Label(outer, text="", justify="left", anchor="w", wraplength=500)

        self._instructions_outer = tk.Frame(outer)
        self._setup_scroll = scrolledtext.ScrolledText(
            self._instructions_outer,
            height=15,
            width=66,
            wrap=tk.WORD,
            font=("Arial", 10),
        )
        self._setup_scroll.pack(fill="both", expand=True)
        self._setup_scroll.configure(cursor="arrow")

        # Bottom strip: buttons directly above progress (same for ATAK install, plugin install, etc.)
        self.footer = tk.Frame(outer)
        self.btn_row = tk.Frame(self.footer)
        self.btn_primary = tk.Button(self.btn_row, text="Continue", width=14, command=self._on_primary)
        self.btn_primary.pack(side="right", padx=(8, 0))
        self.btn_secondary = tk.Button(self.btn_row, text="Quit", width=10, command=self.destroy)
        self.btn_secondary.pack(side="right")
        # DEBUG: remove Skip (debug) before release — see module docstring.
        self.btn_skip_debug = tk.Button(self.btn_row, text="Skip (debug)", fg="darkred")

        self.progress = ttk.Progressbar(self.footer, mode="indeterminate")
        try:
            self.progress.configure(cursor="arrow")
        except tk.TclError:
            pass

        self.status = tk.Label(self.footer, text="", anchor="w", justify="left", fg="gray25")

        self.body.pack(fill="both", expand=True, pady=(0, 12))
        self.btn_row.pack(fill="x")
        self.progress.pack(fill="x", pady=(8, 0))
        self.status.pack(fill="x", pady=(4, 0))
        self.footer.pack(fill="x", pady=(12, 0))

        self._step = 0
        self._render_step()

    def _set_busy(self, busy: bool) -> None:
        self.btn_primary.configure(state=("disabled" if busy else "normal"))

    def _show_body_label(self) -> None:
        self._instructions_outer.pack_forget()
        self.body.pack(fill="both", expand=True, pady=(0, 12), before=self.footer)

    def _show_setup_instructions_panel(self) -> None:
        self.body.pack_forget()
        self._instructions_outer.pack(fill="both", expand=True, pady=(0, 12), before=self.footer)
        self._setup_scroll.configure(state="normal")
        self._setup_scroll.delete("1.0", tk.END)
        self._setup_scroll.insert("1.0", ATAK_POST_INSTALL_SETUP_INSTRUCTIONS)
        self._setup_scroll.configure(state="disabled")

    def _render_step(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_skip_debug.pack_forget()

        if self._step == 0:
            self._show_body_label()
            self.step_label.configure(text="")
            extra = ""
            if not self.manifest_url:
                extra = (
                    f"\n\nSet ATAK_DEPLOY_MANIFEST_URL in:\n{DEPLOY_ENV_PATH}\n"
                    "(uncomment the line or add your URL), then run this again.\n"
                )
            self.body.configure(
                text=(
                    "This program is the full install assuming you have not installed ATAK or Imagery. "
                    "The installer will guide you through the process.\n\n"
                    "If you would like to add additional imagery at a later time, run the ATAK Imagery Downloader "
                    "application, as it does not include ATAK installation."
                    + extra
                )
            )
            self.btn_primary.configure(text="Continue", command=lambda: self._advance(1))
            self.status.configure(text="")

        elif self._step == 1:
            self._show_body_label()
            self.step_label.configure(text="Connect your Android device")
            self.body.configure(
                text=(
                    "1. On the phone, enable Developer options and USB debugging.\n"
                    "2. Connect USB\n"
                    "3. Select USB Mode, File Transfer\n\n"
                    "Click Continue to verify that adb sees your device."
                )
            )
            self.btn_primary.configure(state="normal", text="Continue", command=self._step_connect_check)
            self.status.configure(text="")

        elif self._step == 2:
            self._show_body_label()
            self.step_label.configure(text="Installing ATAK")
            self.body.configure(
                text="Downloading the ATAK build from your server and installing it with adb."
            )
            self.progress.pack(fill="x", pady=(8, 0), before=self.status)
            self.btn_skip_debug.configure(command=self._on_debug_skip_atak_install)
            self.btn_skip_debug.pack(side="left", padx=(0, 8))
            self.btn_primary.configure(state="disabled", text="Working…")
            self._begin_install_atak()

        elif self._step == 3:
            self._show_setup_instructions_panel()
            self.step_label.configure(text="Complete ATAK setup on device")
            self.btn_primary.configure(state="normal", text="Continue", command=lambda: self._advance(4))
            self.status.configure(text="")

        elif self._step == 4:
            self._show_body_label()
            self.step_label.configure(text="Installing plugin")
            self.body.configure(text="Installing the ATAK plugin from your build.")
            self.progress.pack(fill="x", pady=(8, 0), before=self.status)
            self.btn_skip_debug.configure(command=self._on_debug_skip_plugin_install)
            self.btn_skip_debug.pack(side="left", padx=(0, 8))
            self.btn_primary.configure(state="disabled", text="Working…")
            self._begin_install_plugin()

    def _on_primary(self) -> None:
        pass

    def _advance(self, n: int) -> None:
        self._step = n
        self._render_step()

    def _step_connect_check(self) -> None:
        if not self.manifest_url:
            messagebox.showerror(
                APP_TITLE,
                f"ATAK_DEPLOY_MANIFEST_URL is not set.\n\n"
                f"Edit this file and add your manifest URL (not commented):\n{DEPLOY_ENV_PATH}\n\n"
                f"Same folder: deploy.env.example shows the expected format.",
            )
            return

        if not adb_available():
            messagebox.showerror(
                APP_TITLE,
                "adb was not found. Install Android platform tools (adb) and ensure it is on PATH.",
            )
            return

        devices = list_usb_devices()
        serial = pick_serial(devices)
        if serial is None and len(devices) > 1:
            serial = self._ask_serial_choice(devices)
        if not serial:
            detail = adb_devices_human_summary()
            if len(detail) > 2400:
                detail = detail[:2400] + "\n…"
            messagebox.showwarning(
                APP_TITLE,
                "No Android device in the *device* state (ready for adb).\n\n"
                "If the phone shows “unauthorized”, unlock it and accept the USB debugging "
                "prompt. If you see “no permissions”, install udev rules for adb.\n\n"
                f"{detail}",
            )
            return

        self.selected_serial = serial
        os.environ["ANDROID_SERIAL"] = serial
        self._advance(2)

    def _ask_serial_choice(self, devices: List[str]) -> Optional[str]:
        top = tk.Toplevel(self)
        top.title("Select device")
        top.configure(cursor="arrow")
        top.transient(self)
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
        self.wait_window(top)
        return choice[0]

    def _cleanup_temp_apks(self) -> None:
        for p in (self._atak_apk_temp, self._plugin_apk_temp):
            if p and p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    def _begin_install_atak(self) -> None:
        def work() -> None:
            err: List[Optional[Exception]] = [None]
            try:
                manifest = fetch_manifest(self.manifest_url)
                self.after(0, lambda m=manifest: setattr(self, "_manifest_cache", m))
                apk_path, version, is_temp = resolve_atak_apk(manifest, self.manifest_url)
                self._atak_apk_temp = apk_path if is_temp else None
                self._atak_version_value = str(version)

                def ui_install(msg: str) -> None:
                    self.after(0, lambda m=msg: self.status.configure(text=m))

                self.after(0, self.progress.start, 8)
                install_apk(self.selected_serial, apk_path, ui_install)
                self.after(0, self.progress.stop)
                if is_temp:
                    try:
                        apk_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                self._atak_apk_temp = None
                if self.report_url:
                    safe_post_report(
                        self.report_url,
                        env_optional("ATAK_DEPLOY_API_TOKEN") or None,
                        self._atak_version_value,
                        "",
                        self.selected_serial or "",
                        "atak_installed",
                    )
            except Exception as e:
                err[0] = e
                log(traceback.format_exc())
            finally:
                self.after(0, lambda: self._after_install_atak(err[0]))

        threading.Thread(target=work, daemon=True).start()

    def _on_debug_skip_atak_install(self) -> None:
        """Bypass ATAK APK download/install for local wizard debugging. REMOVE before release."""
        log("DEBUG: Skip (debug) — bypassing ATAK download/install")
        self._debug_skip_atak_pending = True
        try:
            self.progress.stop()
        except Exception:
            pass
        if not self._atak_version_value:
            self._atak_version_value = "debug-skip"
        if not self._manifest_cache and self.manifest_url:
            try:
                self._manifest_cache = fetch_manifest(self.manifest_url)
            except Exception as exc:
                log(f"DEBUG skip: could not prefetch manifest (plugin step may fetch later): {exc}")
        self._advance(3)

    def _on_debug_skip_plugin_install(self) -> None:
        """Bypass plugin APK download/install for local wizard debugging. REMOVE before release."""
        log("DEBUG: Skip (debug) — bypassing plugin download/install")
        self._debug_skip_plugin_pending = True
        try:
            self.progress.stop()
        except Exception:
            pass
        if not self._plugin_report_label:
            self._plugin_report_label = "debug-skip"
        self._finish_and_launch_downloader()

    def _after_install_atak(self, err: Optional[Exception]) -> None:
        if self._debug_skip_atak_pending:
            self._debug_skip_atak_pending = False
            try:
                self.progress.stop()
            except Exception:
                pass
            return

        if err:
            self.progress.stop()
            self._step = 0
            self._cleanup_temp_apks()
            messagebox.showerror(APP_TITLE, f"Could not install ATAK:\n{err}")
            self._render_step()
            return
        try:
            launch_atak(self.selected_serial or "")
        except Exception:
            log("launch_atak after ATAK install failed (user can open ATAK manually)")
        self._advance(3)

    def _begin_install_plugin(self) -> None:
        ser = self.selected_serial or ""

        def work() -> None:
            err: List[Optional[Exception]] = [None]
            try:
                try:
                    launch_atak(ser)
                    time.sleep(1.5)
                except Exception:
                    log("launch_atak before plugin install failed")

                manifest = self._manifest_cache or fetch_manifest(self.manifest_url)
                apk_path, report_label, is_temp = resolve_plugin_apk(manifest, self.manifest_url)
                self._plugin_apk_temp = apk_path if is_temp else None
                self._plugin_report_label = report_label

                def ui_install(msg: str) -> None:
                    self.after(0, lambda m=msg: self.status.configure(text=m))

                self.after(0, self.progress.start, 8)
                install_apk(self.selected_serial, apk_path, ui_install)
                self.after(0, self.progress.stop)

                if self.report_url:
                    safe_post_report(
                        self.report_url,
                        env_optional("ATAK_DEPLOY_API_TOKEN") or None,
                        self._atak_version_value,
                        self._plugin_report_label,
                        self.selected_serial or "",
                        "complete",
                    )
            except Exception as e:
                err[0] = e
                log(traceback.format_exc())
            finally:
                self.after(0, lambda: self._after_install_plugin(err[0]))

        threading.Thread(target=work, daemon=True).start()

    def _after_install_plugin(self, err: Optional[Exception]) -> None:
        self.progress.stop()
        if self._debug_skip_plugin_pending:
            self._debug_skip_plugin_pending = False
            try:
                self.progress.stop()
            except Exception:
                pass
            return

        if err:
            self._cleanup_temp_apks()
            messagebox.showerror(APP_TITLE, f"Could not install plugin:\n{err}")
            self._step = 3
            self._render_step()
            return
        self._cleanup_temp_apks()
        self._finish_and_launch_downloader()

    def _finish_and_launch_downloader(self) -> None:
        """Start ATAK Imagery Downloader without an extra wizard step (avoids a flash of a dummy screen)."""
        try:
            self.progress.stop()
            self.progress.pack_forget()
        except Exception:
            pass
        self.after_idle(self._launch_downloader)

    def _launch_downloader(self) -> None:
        try:
            subprocess.Popen([sys.executable, str(DOWNLOADER)])
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Failed to start downloader:\n{e}")
        self.destroy()


def main() -> None:
    if tk is None or scrolledtext is None:
        print("tkinter is required for this wizard.", file=sys.stderr)
        sys.exit(1)
    ensure_gui_path_for_adb()
    load_deploy_env_file()
    w = DeployWizard()
    w.mainloop()


if __name__ == "__main__":
    main()
