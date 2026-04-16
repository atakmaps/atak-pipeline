# Release Checklist

## Source
- [ ] Linux pipeline tested end-to-end
- [ ] Source changes committed and pushed
- [ ] No generated data committed
- [ ] .gitignore still excludes build/runtime artifacts

## Windows EXE
- [ ] Fresh Windows source folder synced from GitHub
- [ ] Duplicate root-level runtime scripts deleted
- [ ] PyInstaller EXE rebuilt successfully
- [ ] EXE tested through downloader -> SQLite -> DTED

## Windows Installer
- [ ] Inno Setup installer rebuilt successfully
- [ ] Installer tested on Windows

## Release assets
- [ ] Linux asset named clearly (atak-linux-install.zip)
- [ ] Windows asset present (ATAKPipelineSetup.exe)
- [ ] Both assets attached to the intended release
