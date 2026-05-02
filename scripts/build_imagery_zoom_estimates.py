#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import requests

from imagery_tile_selection import STATE_BOUNDARY_BUFFER_MILES, build_tiles_for_state

STATE_GEOJSON_URL = "https://eric.clst.org/assets/wiki/uploads/Stuff/gz_2010_us_040_00_500k.json"
USER_AGENT = "ATAK-Ortho-ZoomEstimate-Builder/1.0"

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

STATE_GEOJSON_PATH = DATA_DIR / "us_states.geojson"
ZOOM_ESTIMATE_PATH = DATA_DIR / "zoom_estimates_z10_z16.json"

AVG_TILE_SIZE = {
    10: 20000,
    11: 22000,
    12: 25000,
    13: 28000,
    14: 32000,
    15: 38000,
    16: 45000,
}


def log(msg: str) -> None:
    print(msg, flush=True)


def download_state_geojson() -> None:
    log(f"Downloading state boundaries -> {STATE_GEOJSON_PATH}")
    with requests.get(STATE_GEOJSON_URL, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with open(STATE_GEOJSON_PATH, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)


def load_states() -> Dict[str, List[List[Tuple[float, float]]]]:
    with open(STATE_GEOJSON_PATH, "r", encoding="utf-8") as f:
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

        if name and rings and name != "District of Columbia":
            states[name] = rings
    return states


def main() -> int:
    download_state_geojson()
    states = load_states()

    payload: Dict[str, object] = {
        "version": 2,
        "generated_utc": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "zoom_min": 10,
        "zoom_max": 16,
        "boundary_buffer_miles": STATE_BOUNDARY_BUFFER_MILES,
        "avg_tile_size_bytes": AVG_TILE_SIZE,
        "states": {},
    }

    total_states = len(states)
    for idx, state_name in enumerate(sorted(states.keys()), start=1):
        log(f"[{idx}/{total_states}] {state_name}")
        rings = states[state_name]
        per_zoom: Dict[str, Dict[str, int]] = {}
        for z in range(10, 17):
            tile_count = len(build_tiles_for_state(rings, z))
            est_bytes = tile_count * AVG_TILE_SIZE[z]
            per_zoom[str(z)] = {
                "estimated_tiles": tile_count,
                "estimated_bytes": est_bytes,
            }
            log(f"  zoom {z}: ~{tile_count:,} tiles, ~{est_bytes:,} bytes")
        payload["states"][state_name] = per_zoom  # type: ignore[index]

    tmp_path = ZOOM_ESTIMATE_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    tmp_path.replace(ZOOM_ESTIMATE_PATH)

    log("")
    log(f"Wrote: {STATE_GEOJSON_PATH}")
    log(f"Wrote: {ZOOM_ESTIMATE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
