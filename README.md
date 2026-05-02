# ATAK Imagery

Cross-platform ATAK imagery pipeline with simple one-click install.

## Linux: run `install_linux.sh` first

On Linux, **always run the installer before using the apps**. The file **`install_linux.sh`** in the **project root** (same folder as `README.md`) prepares **both** programs—**ATAK Device Install** and **Imagery Downloader**—and the Python environment they rely on. Skipping it and running the `.py` files by hand will usually fail or miss dependencies.

Source repository: `https://github.com/atakmaps/atak-imagery`

### How to run the installer

1. Put the project on your machine (clone the repo or extract a release zip) and open a **terminal**.
2. Change to the project root, the directory that contains `install_linux.sh`:

   ```bash
   cd /path/to/atak-imagery
   ```

3. If the script is not marked executable, run:

   ```bash
   chmod +x install_linux.sh
   ```

4. Start the install:

   ```bash
   ./install_linux.sh
   ```

   Some file managers can run the script with a double-click; if nothing happens or you only see a flash, use a terminal and the commands above. The script may ask for **`sudo`** so it can install system packages (Python 3, Tk, Zenity, **adb**, venv support, and related distro packages).

### What `install_linux.sh` does

The root script runs **`scripts/install_linux.sh`**, which:

- Installs or checks **system packages** needed for the pipeline (Python 3, pip/venv, Tkinter, Zenity, Android **adb**, etc.) via apt, dnf, or pacman when it recognizes your distro.
- Creates or repairs a **virtual environment** at **`.venv/`** and installs Python dependencies from **`requirements.txt`**.
- Copies **`deploy.env.example`** to **`deploy.env`** the first time, so **ATAK Device Install** has a config template to edit.
- Writes **`run_atak_pipeline_with_device.sh`** and **`run_atak_pipeline.sh`** in the project root (wrappers that call the correct Python entry points with that venv).
- Installs **two desktop shortcuts** (under `~/.local/share/applications/` and on `~/Desktop` when it exists):
  - **ATAK Device Install** — USB setup: install ATAK and your plugin on the phone, then continue into the map workflow.
  - **Imagery Downloader** — download imagery and build packages when the device is already configured.

After a successful run, use those desktop entries or the two shell scripts above. You only need to run **`install_linux.sh`** again if you move the tree, recreate the venv, or need to refresh system/Python dependencies.

---

## Current stable release (Linux / source)

**Linux / source release:** `v0.2.9` (this tag on GitHub).

**Windows:** A new Windows packaged build is **not** included in this cycle. **Use Windows release `2.8`** until a newer Windows installer is published.

This release includes:

- **ATAK Device Install** (desktop entry): USB steps clarified; ATAK + plugin install over ADB; hands off to Imagery Downloader
- **Imagery Downloader**: temporary install folder defaults to Downloads and remembers last choice; zoom dialog storage note with proper text wrapping
- **DTED step**: pushes merged SQLite and DTED zip to the device under `/sdcard/atak/imagery` and `/sdcard/atak/DTED` (override with `ATAK_DEVICE_FILES_ROOT`); post-build **Yes/No** raw-imagery cleanup; adb restart of ATAK and completion dialog
- **Installer**: `deploy.env.example` seed; portable root paths in root launchers

---

## Overview

This project provides a streamlined pipeline for:

- imagery download
- SQLite creation for ATAK imagery packages
- DTED package download
- final ATAK-ready output packaging

Primary Linux/source scripts:

- `scripts/atak_downloader_finalbuild.py`
- `scripts/atak_imagery_sqlite_builder_finalbuild.py`
- `scripts/atak_dted_downloader.py`

Windows-specific build copies:

- `windows_build/atak_downloader_finalbuild_win.py`
- `windows_build/atak_imagery_sqlite_builder_finalbuild_win.py`
- `windows_build/atak_dted_downloader_win.py`

---

## Critical Project Rule

**Do not treat Linux runtime scripts and Windows EXE scripts as the same thing anymore.**

### Linux / source truth

Linux runtime and source-truth pipeline live in:

```text
scripts/
```
