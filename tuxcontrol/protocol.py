"""Browser integration: which app opens N-central/N-sight "Remote Control" links.

When you click Remote Control in N-central or N-sight, the browser hands a
custom-scheme URL to whatever desktop entry claims ``x-scheme-handler/<scheme>``.
N-able's ``protocolRegister.sh`` sets that up. This module checks it actually
took, and can point the scheme back at the right entry if something else
(another Wine app, a stale entry) has grabbed it.
"""

import configparser
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .wine import TAKE_CONTROL_NAMES


def application_dirs() -> list:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [Path(data_home) / "applications"]
    dirs += [Path(d) / "applications" for d in data_dirs.split(":") if d]
    return dirs


@dataclass
class HandlerEntry:
    desktop_id: str
    path: Path
    name: str
    exec_line: str
    schemes: tuple


def parse_desktop_entry(text: str):
    """Return (Name, Exec, [schemes]) or None if not a usable entry."""
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read_string(text)
    except configparser.Error:
        return None
    if "Desktop Entry" not in cp:
        return None
    sec = cp["Desktop Entry"]
    mimes = [m.strip() for m in sec.get("MimeType", "").split(";") if m.strip()]
    schemes = tuple(m.split("/", 1)[1] for m in mimes if m.startswith("x-scheme-handler/"))
    return sec.get("Name", ""), sec.get("Exec", ""), schemes


def find_handlers(dirs=None) -> list:
    """Desktop entries that look like Take Control and claim a URL scheme."""
    out, seen = [], set()
    for d in dirs if dirs is not None else application_dirs():
        if not d.is_dir():
            continue
        for path in sorted(d.rglob("*.desktop")):
            desktop_id = str(path.relative_to(d)).replace(os.sep, "-")
            if desktop_id in seen:
                continue  # earlier dirs shadow later ones, per the XDG spec
            try:
                parsed = parse_desktop_entry(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if not parsed:
                continue
            name, exec_line, schemes = parsed
            if not schemes:
                continue
            if not (TAKE_CONTROL_NAMES.search(name) or TAKE_CONTROL_NAMES.search(exec_line)
                    or TAKE_CONTROL_NAMES.search(path.name)):
                continue
            seen.add(desktop_id)
            out.append(HandlerEntry(desktop_id, path, name, exec_line, schemes))
    return out


def query_default(scheme: str, run=subprocess.run):
    if not shutil.which("xdg-mime"):
        return None
    try:
        res = run(["xdg-mime", "query", "default", f"x-scheme-handler/{scheme}"],
                  capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.strip() or None


def set_default_argv(scheme: str, desktop_id: str) -> list:
    return ["xdg-mime", "default", desktop_id, f"x-scheme-handler/{scheme}"]


def set_default(scheme: str, desktop_id: str, run=subprocess.run):
    res = run(set_default_argv(scheme, desktop_id), capture_output=True, text=True, timeout=15)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "xdg-mime failed")
