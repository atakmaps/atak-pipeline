#!/usr/bin/env python3
"""
Precompute Web Mercator tile (x, y) lists per US state and zoom for the imagery downloader.

Writes gzip binary caches under scripts/data/tile_plans/v1/*.tiles.gz (see imagery_tile_selection).
Run once before a release (or after changing us_states.geojson / boundary buffer); the downloader
loads these instantly instead of scanning huge tile rectangles at runtime.

Examples:
  python3 scripts/build_tile_plan_cache.py
  python3 scripts/build_tile_plan_cache.py --states Arkansas,Texas
  python3 scripts/build_tile_plan_cache.py --zooms 14,15,16
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from imagery_tile_selection import (  # noqa: E402
    DEFAULT_BOUNDARY_BUFFER_M,
    STATE_BOUNDARY_BUFFER_MILES,
    crc32_file,
    save_tile_plan_cache,
    _compute_tiles_for_state,
)

DATA_DIR = SCRIPT_DIR / "data"
STATE_GEOJSON_PATH = DATA_DIR / "us_states.geojson"
TILE_PLAN_DIR = DATA_DIR / "tile_plans" / "v1"


def load_states(geojson_path: Path) -> Dict[str, List[List[Tuple[float, float]]]]:
    with geojson_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    states: Dict[str, List[List[Tuple[float, float]]]] = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        name = props.get("NAME") or props.get("NAME10") or props.get("STATE_NAME")
        geom = feature.get("geometry", {})
        gtype = geom.get("type")
        coords = geom.get("coordinates", [])

        rings: List[List[Tuple[float, float]]] = []
        if gtype == "Polygon":
            if coords:
                rings.append([(float(x), float(y)) for x, y in coords[0]])
        elif gtype == "MultiPolygon":
            for poly in coords:
                if poly:
                    rings.append([(float(x), float(y)) for x, y in poly[0]])

        if name and rings:
            states[name] = rings
    return states


def main() -> int:
    ap = argparse.ArgumentParser(description="Build tile plan .tiles.gz caches for imagery downloader.")
    ap.add_argument(
        "--states",
        type=str,
        default="",
        help="Comma-separated state names (default: all in GeoJSON). Example: Arkansas,Texas",
    )
    ap.add_argument(
        "--zooms",
        type=str,
        default="10,11,12,13,14,15,16",
        help="Comma-separated zoom levels (default: 10-16).",
    )
    ap.add_argument(
        "--geojson",
        type=Path,
        default=STATE_GEOJSON_PATH,
        help=f"State boundaries GeoJSON (default: {STATE_GEOJSON_PATH})",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=TILE_PLAN_DIR,
        help=f"Output directory (default: {TILE_PLAN_DIR})",
    )
    args = ap.parse_args()

    if not args.geojson.is_file():
        print(f"Missing GeoJSON: {args.geojson}", file=sys.stderr)
        return 1

    zooms = [int(z.strip()) for z in args.zooms.split(",") if z.strip()]
    if not zooms:
        print("No zoom levels.", file=sys.stderr)
        return 1

    states = load_states(args.geojson)
    if args.states.strip():
        wanted = {s.strip() for s in args.states.split(",") if s.strip()}
        missing = wanted - set(states.keys())
        if missing:
            print(f"Unknown state names: {sorted(missing)}", file=sys.stderr)
            return 1
        states = {k: v for k, v in states.items() if k in wanted}

    crc = crc32_file(args.geojson)
    buf = DEFAULT_BOUNDARY_BUFFER_M
    print(
        f"GeoJSON: {args.geojson}\n"
        f"CRC-32: {crc:#010x}\n"
        f"Buffer: {STATE_BOUNDARY_BUFFER_MILES:g} mi ({buf:.1f} m)\n"
        f"States: {len(states)}  Zooms: {zooms}\n"
        f"Output: {args.out_dir}\n",
        flush=True,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    state_list = sorted(states.keys())
    for si, state_name in enumerate(state_list, start=1):
        rings = states[state_name]
        for z in zooms:
            t0 = time.perf_counter()
            tiles = _compute_tiles_for_state(rings, z, buf)
            elapsed = time.perf_counter() - t0
            out = args.out_dir / f"{state_name.replace('/', '_')}_z{z}.tiles.gz"
            save_tile_plan_cache(out, z, buf, crc, tiles)
            print(
                f"[{si}/{len(state_list)}] {state_name} z{z}: {len(tiles):,} tiles in {elapsed:.1f}s -> {out.name}",
                flush=True,
            )

    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
