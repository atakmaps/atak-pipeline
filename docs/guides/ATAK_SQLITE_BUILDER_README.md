# ATAK SQLite Builder README

## Purpose
Takes one downloaded state/source imagery folder and builds a single ATAK-style SQLite cache.

## Final behavior
- imports all numeric zoom folders found under the selected source
- automatically creates folder:
  `atak_<source>`
- output SQLite inside is named:
  `<source>.sqlite`

## Run
```bash
python3 atak_imagery_sqlite_builder_finalbuild.py
```

## CLI example
```bash
python3 atak_imagery_sqlite_builder_finalbuild.py /path/to/StateFolder /path/to/output
```

## Important implementation details
- osmdroid/ATAK SQL key formula is used
- duplicate tiles are replaced, not duplicated
- provider is stored per tile
- timestamped log file is written to `~/.atak_pipeline_logs`
