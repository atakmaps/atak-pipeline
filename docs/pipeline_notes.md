# Pipeline Notes

## Scope
This project preserves a validated ATAK imagery and terrain preparation workflow.

## Guardrails
- Keep working code stable
- Avoid unnecessary refactors
- Prefer full replacement files over partial edits
- Prefer copy/paste command blocks for reproducibility

## Data policy
The repo is intentionally code-only.

Do not include:
- DTED files
- DEM GeoTIFFs
- SQLite outputs
- zipped data products
- temporary download folders

## Operational notes
- Border DTED tiles are copied into every intersecting state
- Hawaii conversion is handled separately from official Hawaii DEM GeoTIFF inputs
- Alaska high-lat lower-resolution exceptions are accepted when documented by the verifier
