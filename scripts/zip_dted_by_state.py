#!/usr/bin/env python3
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path("/media/paul/ExtraDrive/Map/DTED_by_state").resolve()


def log(msg: str) -> None:
    print(msg, flush=True)


def iter_state_dirs(root: Path):
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if child.is_dir():
            yield child


def zip_state_folder(state_dir: Path) -> Path:
    zip_path = state_dir / f"{state_dir.name}.zip"

    files_to_zip = []
    for item in state_dir.rglob("*"):
        if item == zip_path:
            continue
        if item.is_file() and item.suffix.lower() != ".zip":
            files_to_zip.append(item)

    if not files_to_zip:
        log(f"SKIP {state_dir.name}: no non-zip files found")
        return zip_path

    log(f"ZIPPING {state_dir.name} -> {zip_path}")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
        for file_path in files_to_zip:
            arcname = file_path.relative_to(state_dir)
            zf.write(file_path, arcname.as_posix())

    return zip_path


def cleanup_state_folder(state_dir: Path, zip_path: Path) -> None:
    for item in sorted(state_dir.iterdir(), key=lambda p: p.name.lower(), reverse=True):
        if item == zip_path:
            continue

        if item.is_file():
            log(f"DELETE FILE {item}")
            item.unlink()
        elif item.is_dir():
            for sub in sorted(item.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if sub.is_file():
                    sub.unlink()
                elif sub.is_dir():
                    try:
                        sub.rmdir()
                    except OSError:
                        pass
            try:
                item.rmdir()
            except OSError:
                pass


def main() -> int:
    if not ROOT.is_dir():
        print(f"ERROR: folder not found: {ROOT}", file=sys.stderr)
        return 1

    state_dirs = list(iter_state_dirs(ROOT))
    if not state_dirs:
        print(f"ERROR: no state folders found under: {ROOT}", file=sys.stderr)
        return 1

    log(f"ROOT: {ROOT}")
    log(f"FOUND {len(state_dirs)} state folders")
    log("")

    for state_dir in state_dirs:
        zip_path = zip_state_folder(state_dir)
        if zip_path.exists():
            cleanup_state_folder(state_dir, zip_path)
            log(f"DONE {state_dir.name}")
            log("")

    log("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
