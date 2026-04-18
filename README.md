# ATAK Pipeline

Cross-platform ATAK imagery pipeline with simple one-click install.

## Overview

This project provides a streamlined pipeline for:

- imagery download
- SQLite creation for ATAK imagery packages

Included scripts:
- atak_downloader_finalbuild.py
- atak_imagery_sqlite_builder_finalbuild.py

## Quick Start

1. Go to:
https://github.com/atakmaps/atak-pipeline/releases

2. Download the latest zip

3. Extract it

## Linux
./install_linux.sh

## Windows
Double-click:
install_windows.cmd

## Notes
- First run installs dependencies
- Then launches the imagery downloader

## Platform Builds

### Linux
Run:

./run_atak_pipeline.sh

See docs/RUN_LINUX.md

### Windows
See docs/BUILD_WINDOWS.md

### Release Assets
Linux: atak-linux-install.zip
Windows: ATAKPipelineSetup.exe

## Output Files (Important)

After the pipeline completes, your final files will be located in:

ATAK_Upload_YYYYMMDD/

This folder contains:
- ATAK_SQL_YYYYMMDD_HHMMSS.sqlite
- dted2_HHMMSS.zip

### What to do next

1. Connect your Android device
2. Copy BOTH files into:

/Download/

3. Open ATAK — it will automatically detect and use the data

### Notes

- The Imagery/ folder is temporary and can be deleted after completion
- You will be prompted to remove it automatically
- The pipeline will open the final folder for you when finished

