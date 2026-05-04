#!/usr/bin/env python3
"""Verify *.tiles.gz under scripts/data/tile_plans/v1 against current us_states.geojson CRC and buffer."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

DATA_DIR = SCRIPTS / "data"
GEOJSON = DATA_DIR / "us_states.geojson"
TILE_PLAN_DIR = DATA_DIR / "tile_plans" / "v1"

from imagery_tile_selection import (  # noqa: E402
    DEFAULT_BOUNDARY_BUFFER_M,
    crc32_file,
    try_load_tile_plan_cache,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dir",
        type=Path,
        default=TILE_PLAN_DIR,
        help=f"Directory of .tiles.gz (default: {TILE_PLAN_DIR})",
    )
    ap.add_argument(
        "--state",
        default="",
        help="Only files for this state name (substring), e.g. Arkansas",
    )
    args = ap.parse_args()
    d: Path = args.dir
    if not GEOJSON.is_file():
        print(f"Missing GeoJSON: {GEOJSON}", file=sys.stderr)
        return 2
    crc = crc32_file(GEOJSON)
    buf = float(DEFAULT_BOUNDARY_BUFFER_M)
    paths = sorted(d.glob("*.tiles.gz"))
    if args.state:
        paths = [p for p in paths if args.state in p.name]
    if not paths:
        print(f"No .tiles.gz in {d}" + (f" matching {args.state!r}" if args.state else ""))
        return 1

    rx = re.compile(r"^(.+)_z(\d+)\.tiles\.gz$")
    bad = 0
    for p in paths:
        m = rx.match(p.name)
        if not m:
            print(f"SKIP bad name: {p.name}")
            bad += 1
            continue
        state, zs = m.group(1), int(m.group(2))
        tiles = try_load_tile_plan_cache(p, zs, buf, crc)
        if tiles is None:
            print(f"FAIL {p.name} (wrong CRC/buffer/zoom or corrupt)")
            bad += 1
            continue
        print(f"OK   {p.name}  ({len(tiles):,} tiles)  state={state} z={zs}")

    print(f"Checked {len(paths)} file(s), {bad} problem(s).")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
