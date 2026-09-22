"""A small JSON record of what TuxControl has installed, for status and uninstall."""

import json
import os
import time
from pathlib import Path

from . import data_dir


def state_path() -> Path:
    return data_dir() / "state.json"


def load(path: Path = None) -> dict:
    try:
        return json.loads((path or state_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data: dict, path: Path = None):
    p = path or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def record_install(kind: str, staged, path: Path = None):
    data = load(path)
    data[kind] = {
        "bundle": str(staged.root),
        "sha256": staged.sha256,
        "source": staged.source,
        "installed_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    save(data, path)


def forget(kind: str, path: Path = None):
    data = load(path)
    if data.pop(kind, None) is not None:
        save(data, path)
