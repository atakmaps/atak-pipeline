"""
Tile coverage for USGS orthophoto downloads vs state GeoJSON rings.

- Includes a tile when its Web Mercator center lies inside the state polygon, OR
  when that center is within ``boundary_buffer_m`` meters of any polygon edge
  (extra imagery past the nominal boundary so boundary lines stay visible).

Precomputed tile lists (per state, per zoom) live under ``data/tile_plans/v1/`` as
``.tiles.gz`` files; build them with ``scripts/build_tile_plan_cache.py``. At
runtime, ``build_tiles_for_state`` loads a cache when ``geojson_path`` and
``tile_plan_dir`` are set and the file matches the current boundary GeoJSON CRC
and buffer distance.
"""
from __future__ import annotations

import gzip
import math
import struct
import zlib
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

# Miles beyond the GeoJSON boundary to keep imagery for (edge tiles + visibility).
STATE_BOUNDARY_BUFFER_MILES = 3.0
METERS_PER_MILE = 1609.344
DEFAULT_BOUNDARY_BUFFER_M = STATE_BOUNDARY_BUFFER_MILES * METERS_PER_MILE

_SEGMENT_SAMPLES = 16

# Gzip tile list cache: magic, format, zoom, geojson_crc32, boundary_m (double), n, then n*(x,y) uint32 pairs.
_TILE_PLAN_MAGIC = b"ATKP"
_TILE_PLAN_FORMAT = 1
_TILE_PLAN_HEADER = struct.Struct("!4sIIIdI")  # 28 bytes


def crc32_file(path: Path) -> int:
    """CRC-32 of file bytes (unsigned)."""
    h = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h = zlib.crc32(chunk, h)
    return h & 0xFFFFFFFF


def _tile_plan_cache_path(tile_plan_dir: Path, state_name: str, zoom: int) -> Path:
    safe = state_name.replace("/", "_")
    return tile_plan_dir / f"{safe}_z{zoom}.tiles.gz"


def try_load_tile_plan_cache(
    cache_path: Path,
    zoom: int,
    boundary_buffer_m: float,
    geojson_crc32: int,
) -> Optional[List[Tuple[int, int]]]:
    if not cache_path.is_file():
        return None
    try:
        raw = gzip.decompress(cache_path.read_bytes())
    except (OSError, EOFError, gzip.BadGzipFile):
        return None
    if len(raw) < _TILE_PLAN_HEADER.size:
        return None
    magic, fmt, z, crc, buf_m, n = _TILE_PLAN_HEADER.unpack_from(raw, 0)
    if magic != _TILE_PLAN_MAGIC or fmt != _TILE_PLAN_FORMAT or z != zoom or crc != geojson_crc32:
        return None
    if abs(buf_m - boundary_buffer_m) > 1e-6:
        return None
    body = raw[_TILE_PLAN_HEADER.size :]
    if len(body) != n * 8:
        return None
    tiles: List[Tuple[int, int]] = []
    off = 0
    for _ in range(n):
        x, y = struct.unpack_from("!II", body, off)
        off += 8
        tiles.append((x, y))
    return tiles


def save_tile_plan_cache(
    cache_path: Path,
    zoom: int,
    boundary_buffer_m: float,
    geojson_crc32: int,
    tiles: List[Tuple[int, int]],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    header = _TILE_PLAN_HEADER.pack(
        _TILE_PLAN_MAGIC,
        _TILE_PLAN_FORMAT,
        zoom,
        geojson_crc32 & 0xFFFFFFFF,
        float(boundary_buffer_m),
        len(tiles),
    )
    body = b"".join(struct.pack("!II", int(x), int(y)) for x, y in tiles)
    blob = gzip.compress(header + body, compresslevel=6, mtime=0)
    cache_path.write_bytes(blob)


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[int, int]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    xtile = max(0, min(int(n) - 1, xtile))
    ytile = max(0, min(int(n) - 1, ytile))
    return xtile, ytile


def tile_center_lonlat(x: int, y: int, z: int) -> Tuple[float, float]:
    n = 2.0 ** z
    lon_deg = (x + 0.5) / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ((y + 0.5) / n))))
    lat_deg = math.degrees(lat_rad)
    return lon_deg, lat_deg


def bbox_for_rings(rings: List[List[Tuple[float, float]]]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for ring in rings:
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def point_in_ring(lon: float, lat: float, ring: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    x1, y1 = ring[0]
    for i in range(1, n + 1):
        x2, y2 = ring[i % n]
        if ((y1 > lat) != (y2 > lat)):
            xinters = (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1
            if lon < xinters:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def point_in_state(lon: float, lat: float, rings: List[List[Tuple[float, float]]]) -> bool:
    return any(point_in_ring(lon, lat, ring) for ring in rings)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters (WGS84 sphere)."""
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlamb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlamb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, h)))


def min_dist_point_to_segment_m(
    lon: float, lat: float, lon1: float, lat1: float, lon2: float, lat2: float
) -> float:
    """Minimum meters from (lon,lat) to segment endpoints and linearly interpolated samples."""
    best = min(
        haversine_m(lat, lon, lat1, lon1),
        haversine_m(lat, lon, lat2, lon2),
    )
    for i in range(1, _SEGMENT_SAMPLES):
        t = i / _SEGMENT_SAMPLES
        lt = lat1 + t * (lat2 - lat1)
        ln = lon1 + t * (lon2 - lon1)
        best = min(best, haversine_m(lat, lon, lt, ln))
    return best


def min_distance_point_to_rings_m(lon: float, lat: float, rings: List[List[Tuple[float, float]]]) -> float:
    best = float("inf")
    for ring in rings:
        n = len(ring)
        if n < 2:
            continue
        for i in range(n):
            lon1, lat1 = ring[i]
            lon2, lat2 = ring[(i + 1) % n]
            best = min(best, min_dist_point_to_segment_m(lon, lat, lon1, lat1, lon2, lat2))
    return best


def expand_bbox_by_buffer_m(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float, buffer_m: float
) -> Tuple[float, float, float, float]:
    if buffer_m <= 0:
        return min_lon, min_lat, max_lon, max_lat
    mid_lat = (min_lat + max_lat) / 2.0
    cos_lat = max(0.2, math.cos(math.radians(mid_lat)))
    dlat = buffer_m / 111_320.0
    dlon = buffer_m / (111_320.0 * cos_lat)
    return min_lon - dlon, min_lat - dlat, max_lon + dlon, max_lat + dlat


def tile_qualifies(
    lon: float, lat: float, rings: List[List[Tuple[float, float]]], boundary_buffer_m: float
) -> bool:
    if point_in_state(lon, lat, rings):
        return True
    if boundary_buffer_m <= 0:
        return False
    return min_distance_point_to_rings_m(lon, lat, rings) <= boundary_buffer_m


class TilePlanBuildResult(NamedTuple):
    """tiles plus whether they came from a precomputed ``.tiles.gz`` cache."""

    tiles: List[Tuple[int, int]]
    from_cache: bool


def _compute_tiles_for_state(
    rings: List[List[Tuple[float, float]]],
    zoom: int,
    boundary_buffer_m: float,
) -> List[Tuple[int, int]]:
    min_lon, min_lat, max_lon, max_lat = bbox_for_rings(rings)
    min_lon, min_lat, max_lon, max_lat = expand_bbox_by_buffer_m(
        min_lon, min_lat, max_lon, max_lat, boundary_buffer_m
    )

    min_x, max_y = lonlat_to_tile(min_lon, min_lat, zoom)
    max_x, min_y = lonlat_to_tile(max_lon, max_lat, zoom)

    x_start, x_end = sorted((min_x, max_x))
    y_start, y_end = sorted((min_y, max_y))

    tiles: List[Tuple[int, int]] = []
    for x in range(x_start, x_end + 1):
        for y in range(y_start, y_end + 1):
            lon, lat = tile_center_lonlat(x, y, zoom)
            if tile_qualifies(lon, lat, rings, boundary_buffer_m):
                tiles.append((x, y))
    return tiles


def build_tiles_for_state_result(
    state_name: str,
    rings: List[List[Tuple[float, float]]],
    zoom: int,
    boundary_buffer_m: Optional[float] = None,
    *,
    geojson_path: Optional[Path] = None,
    tile_plan_dir: Optional[Path] = None,
) -> TilePlanBuildResult:
    """
    Like ``build_tiles_for_state`` but reports whether the list came from disk cache.
    """
    buf = DEFAULT_BOUNDARY_BUFFER_M if boundary_buffer_m is None else float(boundary_buffer_m)

    if geojson_path is not None and tile_plan_dir is not None and geojson_path.is_file():
        crc = crc32_file(geojson_path)
        cache_path = _tile_plan_cache_path(tile_plan_dir, state_name, zoom)
        cached = try_load_tile_plan_cache(cache_path, zoom, buf, crc)
        if cached is not None:
            return TilePlanBuildResult(cached, True)

    tiles = _compute_tiles_for_state(rings, zoom, buf)
    return TilePlanBuildResult(tiles, False)


def build_tiles_for_state(
    state_name: str,
    rings: List[List[Tuple[float, float]]],
    zoom: int,
    boundary_buffer_m: Optional[float] = None,
    *,
    geojson_path: Optional[Path] = None,
    tile_plan_dir: Optional[Path] = None,
) -> List[Tuple[int, int]]:
    """
    Return (x, y) tile indices whose centers lie inside the state polygon or within
    ``boundary_buffer_m`` meters of its boundary (Web Mercator tile grid at ``zoom``).

    When ``geojson_path`` and ``tile_plan_dir`` are set and a matching ``.tiles.gz``
    cache exists (same GeoJSON CRC-32 and buffer), returns the cached list immediately.
    Otherwise computes the list (slow for large states at high zoom).
    """
    return build_tiles_for_state_result(
        state_name,
        rings,
        zoom,
        boundary_buffer_m,
        geojson_path=geojson_path,
        tile_plan_dir=tile_plan_dir,
    ).tiles
