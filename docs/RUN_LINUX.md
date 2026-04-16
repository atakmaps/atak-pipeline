# Run ATAK Pipeline on Linux

## Install / setup
From the repo root:

./install_linux.sh

## Run
From the repo root:

./run_atak_pipeline.sh

## What happens
1. Imagery downloader launches
2. User selects one or more states
3. Imagery is downloaded under an automatically created Imagery/ folder
4. last_imagery_root.txt is written
5. SQLite builder launches automatically and builds all valid state folders
6. DTED downloader launches automatically and uses the same saved imagery root

## Important behavior
- Runtime scripts live in scripts/
- Do not keep duplicate root-level copies of the runtime scripts
- last_imagery_root.txt is generated at runtime and should not be committed
