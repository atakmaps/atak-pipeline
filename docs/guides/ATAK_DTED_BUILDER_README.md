# ATAK DTED Builder README

## Purpose
Builds DTED Level 2 from DEM GeoTIFF files.

## Final validated fix
This script is the corrected finalbuild version.

### Problems that were fixed
- incorrect high-latitude width at >= 50°
- Tkinter thread update issue
- progress window close warning after completion
- DTED corner-coordinate warning

### Final DTED logic
- `< 50°` latitude: `3601 x 3601`
- `50° to < 70°`: `1801 x 3601`
- `70° to < 75°`: `1201 x 3601`
- `75° to < 80°`: `901 x 3601`
- `>= 80°`: `451 x 3601`

### Critical georeferencing fix
The finalbuild script uses:
- `gdalwarp` to exact cell bounds
- a point-grid `-a_ullr` half-pixel expansion
- then `gdal_translate -of DTED`

This was validated in chat by:
- W155/W156 test run
- no `corner coordinates not properly aligned` warning
- correct `Size is 3601,3601` below 50°
- correct `Size is 1801,3601` at and above 50°

## Run
```bash
python3 atak_dted_builder_finalbuild.py
```
