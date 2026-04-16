#!/usr/bin/env python3
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)

COMMON_FILES = [
    "scripts",
    "requirements.txt",
]

WINDOWS_FILES = [
    "install_windows.cmd",
    "scripts/install_windows.ps1",
]

LINUX_FILES = [
    "install_linux.sh",
    "scripts/install_linux.sh",
]

def copy_structure(target_dir, extra_files):
    for item in COMMON_FILES:
        src = ROOT / item
        dst = target_dir / item
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    for item in extra_files:
        src = ROOT / item
        dst = target_dir / item
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

def make_zip(source_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for file in source_dir.rglob("*"):
            if file.is_file():
                z.write(file, file.relative_to(source_dir))

def build():
    # WINDOWS
    win_dir = DIST / "windows_build"
    if win_dir.exists():
        shutil.rmtree(win_dir)
    win_dir.mkdir()

    copy_structure(win_dir, WINDOWS_FILES)

    win_zip = DIST / "atak-pipeline-windows.zip"
    make_zip(win_dir, win_zip)
    shutil.rmtree(win_dir)

    # LINUX
    lin_dir = DIST / "linux_build"
    if lin_dir.exists():
        shutil.rmtree(lin_dir)
    lin_dir.mkdir()

    copy_structure(lin_dir, LINUX_FILES)

    lin_zip = DIST / "atak-pipeline-linux.zip"
    make_zip(lin_dir, lin_zip)
    shutil.rmtree(lin_dir)

    print("Created:")
    print(win_zip)
    print(lin_zip)

if __name__ == "__main__":
    build()
