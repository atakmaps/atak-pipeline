# GitHub Posting Guide

## What to upload
Upload:
- all `*_finalbuild.py` scripts
- all README files
- the handoff text file
- optional install/setup scripts

Do not upload:
- large downloaded imagery
- large DTED outputs
- large SQLite output files

## Basic steps
```bash
mkdir atak-pipeline
cd atak-pipeline
git init
mkdir scripts
```

Copy the finalbuild scripts into `scripts/`.

Then:
```bash
git add .
git commit -m "Initial ATAK pipeline finalbuild bundle"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

## Suggested `.gitignore`
```gitignore
__pycache__/
*.pyc
logs/
*.log
*.sqlite
DTED2/
DTED_by_state/
*.jpg
*.jpeg
*.png
*.webp
.venv/
env/
```
