"""
Tile coverage for USGS orthophoto downloads vs state GeoJSON rings.

- Includes a tile when its Web Mercator center lies inside the state polygon, OR
  when that center is within ``boundary_buffer_m`` meters of any polygon edge
  (extra imagery past the nominal boundary so boundary lines stay visible).
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

# Miles beyond the GeoJSON boundary to keep imagery for (edge tiles + visibility).
STATE_BOUNDARY_BUFFER_MILES = 3.0
METERS_PER_MILE = 1609.344
DEFAULT_BOUNDARY_BUFFER_M = STATE_BOUNDARY_BUFFER_MILES * METERS_PER_MILE

_SEGMENT_SAMPLES = 16


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


def build_tiles_for_state(
    rings: List[List[Tuple[float, float]]],
    zoom: int,
    boundary_buffer_m: Optional[float] = None,
) -> List[Tuple[int, int]]:
    """
    Return (x, y) tile indices whose centers lie inside the state polygon or within
    ``boundary_buffer_m`` meters of its boundary (Web Mercator tile grid at ``zoom``).
    """
    buf = DEFAULT_BOUNDARY_BUFFER_M if boundary_buffer_m is None else boundary_buffer_m

    min_lon, min_lat, max_lon, max_lat = bbox_for_rings(rings)
    min_lon, min_lat, max_lon, max_lat = expand_bbox_by_buffer_m(min_lon, min_lat, max_lon, max_lat, buf)

    min_x, max_y = lonlat_to_tile(min_lon, min_lat, zoom)
    max_x, min_y = lonlat_to_tile(max_lon, max_lat, zoom)

    x_start, x_end = sorted((min_x, max_x))
    y_start, y_end = sorted((min_y, max_y))

    tiles: List[Tuple[int, int]] = []
    for x in range(x_start, x_end + 1):
        for y in range(y_start, y_end + 1):
            lon, lat = tile_center_lonlat(x, y, zoom)
            if tile_qualifies(lon, lat, rings, buf):
                tiles.append((x, y))
    return tiles
