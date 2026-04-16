#!/usr/bin/env python3
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path("/home/paul/Desktop/ATAK/pipeline").resolve()
VERSION_FILE = ROOT / "VERSION"
DIST_DIR = ROOT / "dist"

EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    ".venv",
}

EXCLUDE_FILES = {
    ".DS_Store",
}

def read_version() -> str:
    if not VERSION_FILE.exists():
        raise FileNotFoundError(f"Missing VERSION file: {VERSION_FILE}")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION file is empty")
    return version

def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.name in EXCLUDE_FILES:
        return True
    return False

def build_zip(version: str) -> Path:
    DIST_DIR.mkdir(exist_ok=True)
    zip_path = DIST_DIR / f"atak-pipeline-v{version}-source.zip"

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in ROOT.rglob("*"):
            if should_skip(item):
                continue
            if item == zip_path:
                continue
            if item.is_dir():
                continue

            rel_path = item.relative_to(ROOT)
            arcname = Path("atak-pipeline") / rel_path
            zf.write(item, arcname.as_posix())

    return zip_path

def main() -> None:
    version = read_version()
    zip_path = build_zip(version)
    print(f"Created: {zip_path}")

if __name__ == "__main__":
    main()
