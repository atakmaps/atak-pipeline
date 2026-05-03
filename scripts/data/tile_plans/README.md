# Tile plan cache (`v1/`)

Precomputed **Web Mercator tile (x, y)** lists for each US state and zoom **10–16** live here as
`*.tiles.gz` files (gzip + small binary header). The imagery downloader loads them when present so
**“Scanning tile coverage…”** does not re-walk huge tile rectangles for large states at high zoom.

## Build caches (maintainers / before release)

From the repo root (or `scripts/`):

```bash
cd scripts
python3 build_tile_plan_cache.py
```

This reads `data/us_states.geojson`, computes every state × zoom, and writes `data/tile_plans/v1/*.tiles.gz`.
A full run can take **hours** on one machine; use filters while testing:

```bash
python3 build_tile_plan_cache.py --states Arkansas --zooms 16
python3 build_tile_plan_cache.py --states Arkansas,Texas --zooms 10,11,12,13,14,15,16
```

Caches are tied to a **CRC-32 of the GeoJSON file** and the **boundary buffer** (miles); if you replace
`us_states.geojson` or change `STATE_BOUNDARY_BUFFER_MILES` in `imagery_tile_selection.py`, rebuild caches.

## Shipping

Include `data/tile_plans/v1/*.tiles.gz` in source trees / release zips so end users never pay the compute cost.
The directory may be empty until caches are generated; the downloader still works (slower first scan).
