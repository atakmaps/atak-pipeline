# ATAK Pipeline

Cross-platform ATAK imagery pipeline with simple one-click install.

## Current Stable Release

**Current release:** `v0.2.5`

This release includes:

- finalized Linux installer flow
- Linux desktop launcher creation after install
- finalized Linux upload-folder workflow
- isolated Windows build system under `windows_build/`
- working Windows EXE flow:
  - downloader
  - SQLite builder
  - DTED downloader

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
