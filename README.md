# ATAK Pipeline

Cross-platform ATAK imagery pipeline with simple one-click install.

## Current stable release (Linux / source)

**Linux / source release:** `v0.2.9` (this tag on GitHub).

**Windows:** A new Windows packaged build is **not** included in this cycle. **Use Windows release `2.8`** until a newer Windows installer is published.

This release includes:

- **Device setup** (`ATAK Pipeline (device setup)`): USB steps clarified; ATAK + plugin install over ADB; hands off to the map pipeline
- **Imagery downloader**: temporary install folder defaults to Downloads and remembers last choice; zoom dialog storage note with proper text wrapping
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
