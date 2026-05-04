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

### Build on the server only

Check out this repo **on the VM**, then run the wrapper (stays on the server; no laptop rsync):

```bash
cd /path/to/atak-imagery   # or your fork path
git pull
chmod +x scripts/tile_plan_cache_on_server.sh
scripts/tile_plan_cache_on_server.sh
```

Detach from SSH but keep the job running:

```bash
nohup scripts/tile_plan_cache_on_server.sh >> /root/tile_plan_cache.log 2>&1 &
tail -f /root/tile_plan_cache.log
```

Copy `scripts/data/tile_plans/v1/*.tiles.gz` to your release tree or laptop when done (`rsync`, `scp`, etc.).

From repo root you can also pull test caches over SSH: `scripts/fetch_tile_plan_caches.sh` (defaults: Arkansas `Arkansas_z*.tiles.gz` from `root@31.220.30.74`). Override with `TILE_PLAN_FETCH_SSH`, `TILE_PLAN_FETCH_REMOTE`, and `TILE_PLAN_FETCH_PATTERN`.

Caches are tied to a **CRC-32 of the GeoJSON file** and the **boundary buffer** (miles); if you replace
`us_states.geojson` or change `STATE_BOUNDARY_BUFFER_MILES` in `imagery_tile_selection.py`, rebuild caches.

## Shipping

Include `data/tile_plans/v1/*.tiles.gz` in source trees / release zips so end users never pay the compute cost.
The directory may be empty until caches are generated; the downloader still works (slower first scan).
