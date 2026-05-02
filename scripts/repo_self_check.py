#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent

required_root = [
    "README.md",
    "VERSION",
    "requirements.txt",
    "install_linux.sh",
    "install_windows.cmd",
    "run_atak_pipeline.sh",
    "run_atak_pipeline_with_device.sh",
    "windows_launcher.py",
    "ATAKPipeline_Setup.iss",
    "deploy.env.example",
]

required_scripts = [
    "scripts/atak_downloader_finalbuild.py",
    "scripts/atak_imagery_sqlite_builder_finalbuild.py",
    "scripts/atak_dted_downloader.py",
    "scripts/atak_adb_deploy.py",
    "scripts/install_linux.sh",
    "scripts/build_release.py",
]

dangerous_duplicates = [
    "atak_downloader_finalbuild.py",
    "atak_imagery_sqlite_builder_finalbuild.py",
    "atak_dted_downloader.py",
]

missing = []
for rel in required_root + required_scripts:
    if not (ROOT / rel).exists():
        missing.append(rel)

duplicates = [f for f in dangerous_duplicates if (ROOT / f).exists()]

print("ATAK Imagery repo self-check")
print("=" * 40)

if missing:
    print("\nMissing files:")
    for m in missing:
        print(" -", m)

if duplicates:
    print("\nDangerous duplicates found:")
    for d in duplicates:
        print(" -", d)

if not missing and not duplicates:
    print("\nEverything looks clean.")

