# ATAK Pipeline Full README

This bundle contains the finalbuild scripts for the four main steps in the workflow:

1. `atak_downloader_finalbuild.py`
   Downloads USGS orthophoto XYZ tiles by state and zoom into:
   `<output parent>/<STATE>/<zoom>/<x>/<y>.jpg`

2. `atak_imagery_sqlite_builder_finalbuild.py`
   Converts one downloaded state/source imagery folder into a single ATAK-style SQLite tile cache.
   Final behavior:
   - automatically creates output folder: `atak_<source>`
   - SQLite filename inside is: `<source>.sqlite`

3. `atak_dted_builder_finalbuild.py`
   Builds nationwide DTED Level 2 from DEM GeoTIFF files.
   This is the corrected version that uses:
   - latitude-aware DTED widths
   - point-grid georeferencing with half-pixel expansion
   - clean DTED output with no corner-coordinate warning after validation

4. `organize_dted_by_state_finalbuild.py`
   Copies DTED into per-state folders while preserving subfolders.

## Recommended order

### Imagery pipeline
- Run downloader
- Confirm state imagery folder looks correct
- Run SQLite builder on that state imagery folder
- Copy the resulting `.sqlite` to ATAK as needed

### Terrain pipeline
- Build DTED2 from DEM GeoTIFF files
- Optionally organize DTED by state

## Typical paths used during development
- Imagery source root: `/media/paul/ExtraDrive/Map`
- DTED output root: `/media/paul/ExtraDrive/Map/DTED2`
- Organizer states file: `/media/paul/ExtraDrive/Map/DTED2/us_states_simple.geojson`

## Dependency notes
Common dependencies used across scripts:
- Python 3.10+
- `requests`
- `geopandas`
- `shapely`
- `pyproj`
- `pyogrio`
- `gdal` / `gdal-bin`
- `tkinter`

## GitHub posting checklist
- Put these scripts at repo root or in `scripts/`
- Add the README files in this bundle
- Add `.gitignore`
- Do not upload huge imagery or DTED outputs
- Do upload:
  - scripts
  - README files
  - setup instructions
  - sample commands
  - any small sample state boundary file if desired

## Suggested repo structure

```text
atak-pipeline/
  README.md
  ATAK_PIPELINE_FULL_README.md
  ATAK_DOWNLOADER_README.md
  ATAK_SQLITE_BUILDER_README.md
  ATAK_DTED_BUILDER_README.md
  ATAK_DTED_ORGANIZER_README.md
  NEXT_CHATGPT_HANDOFF.txt
  scripts/
    atak_downloader_finalbuild.py
    atak_imagery_sqlite_builder_finalbuild.py
    atak_dted_builder_finalbuild.py
    organize_dted_by_state_finalbuild.py
```
