"""NAble TuxControl -- helps Linux IT admins install N-able Take Control.

The package is shared by both front ends (``cli.py`` and ``gui.py``); nothing
in here outside those two modules imports GTK, so the core logic can be tested
headless.
"""

import os
from pathlib import Path

APP_NAME = "NAble TuxControl"
APP_ID = "io.github.tridentspoon.TuxControl"
VERSION = "0.1.0"
REPO = "TridentSpoon/NAble-TuxControl"
REPO_URL = f"https://github.com/{REPO}"


def data_dir() -> Path:
    """Where staged bundles and install records live (per user, never root)."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / "nable-tuxcontrol"
