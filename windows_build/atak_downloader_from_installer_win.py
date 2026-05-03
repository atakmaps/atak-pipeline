#!/usr/bin/env python3
"""Windows: Device Installer entry for imagery pipeline (see Linux ``atak_downloader_from_installer.py``)."""

from __future__ import annotations

import os


def main() -> None:
    os.environ["ATAK_DOWNLOADER_LAUNCHED_FROM_DEVICE_INSTALLER"] = "1"
    import atak_downloader_finalbuild_win as core

    core.main()


if __name__ == "__main__":
    main()
