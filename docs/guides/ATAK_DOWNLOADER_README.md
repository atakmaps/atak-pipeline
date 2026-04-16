# ATAK Downloader README

## Purpose
Downloads USGS orthophoto tiles by state and selected zoom levels.

## Output structure
```text
<output parent>/<STATE>/<zoom>/<x>/<y>.jpg
```

## Final validated behavior
- GUI workflow
- checkbox zoom selection
- no default zooms checked
- automatic state boundary download
- unified logs to `./logs`
- progress window
- skips existing tiles
- progress window closes cleanly after completion

## Run
```bash
python3 atak_downloader_finalbuild.py
```

## Notes
This finalbuild version was recreated from the validated working feature set used in chat:
- checkbox zoom selection
- script name standardized to `atak_downloader.py` during development
- logs fixed
- progress close behavior fixed
