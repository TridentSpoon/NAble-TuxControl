"""Small, careful wrappers around Wine for inspecting and tweaking a prefix.

Rule one: never *create* a prefix by accident. Running any wine command
against a missing prefix silently builds a fresh one (and pops a
"wine-mono" dialog), so every query here checks the prefix exists first.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

TAKE_CONTROL_NAMES = re.compile(
    r"take\s*control|mspa|msp\s*anywhere|n-?able|solarwinds|beanywhere|n-?central|n-?sight",
    re.IGNORECASE)

DECORATION_KEY = r"HKCU\Software\Wine\X11 Driver"


def default_prefix() -> Path:
    return Path(os.environ.get("WINEPREFIX") or Path.home() / ".wine")


def expand_prefix(raw: str) -> Path:
    """Expand $HOME / ${HOME} / ~ in a prefix path pulled out of a script."""
    home = str(Path.home())
    raw = raw.replace("${HOME}", home).replace("$HOME", home)
    return Path(os.path.expanduser(raw))


def prefix_exists(prefix: Path) -> bool:
    return (Path(prefix) / "system.reg").is_file()


def _env(prefix: Path) -> dict:
    env = dict(os.environ)
    env["WINEPREFIX"] = str(prefix)
    env.setdefault("WINEDEBUG", "-all")
    # Don't let a query trigger the Mono/Gecko install prompts.
    env.setdefault("WINEDLLOVERRIDES", "mscoree,mshtml=")
    return env


def _wine(args, prefix: Path, run=subprocess.run, timeout=60):
    if not shutil.which("wine"):
        raise FileNotFoundError("wine is not installed")
    if not prefix_exists(prefix):
        raise FileNotFoundError(f"no Wine prefix at {prefix}")
    return run(["wine", *args], capture_output=True, text=True,
               timeout=timeout, env=_env(prefix))


# -------------------------------------------------------------- uninstallers

def parse_uninstaller_list(text: str) -> list:
    """`wine uninstaller --list` prints `{GUID}|||Display Name` per line."""
    out = []
    for line in text.splitlines():
        if "|||" not in line:
            continue
        guid, _, name = line.partition("|||")
        guid, name = guid.strip(), name.strip()
        if guid:
            out.append((guid, name))
    return out


def list_uninstallers(prefix: Path, run=subprocess.run) -> list:
    res = _wine(["uninstaller", "--list"], prefix, run=run)
    return parse_uninstaller_list(res.stdout)


def take_control_entries(entries) -> list:
    return [(g, n) for g, n in entries if TAKE_CONTROL_NAMES.search(n)]


def uninstall_argv(guid: str) -> list:
    return ["wine", "uninstaller", "--remove", guid]


# ---------------------------------------------------------- decorations

def parse_reg_query(text: str, value: str):
    """Pull a REG_SZ value out of `wine reg query` output; None if absent."""
    rx = re.compile(rf"^\s*{re.escape(value)}\s+REG_SZ\s+(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
    m = rx.search(text or "")
    return m.group(1) if m else None


def decorations_enabled(prefix: Path, run=subprocess.run) -> bool:
    """winecfg's "Allow the window manager to decorate the windows".

    Wine's default when the value is unset is Y (decorated).
    """
    res = _wine(["reg", "query", DECORATION_KEY, "/v", "Decorated"], prefix, run=run)
    val = parse_reg_query(res.stdout, "Decorated")
    return (val or "Y").upper().startswith("Y")


def decorations_argv(enabled: bool) -> list:
    return ["wine", "reg", "add", DECORATION_KEY, "/v", "Decorated",
            "/t", "REG_SZ", "/d", "Y" if enabled else "N", "/f"]


def set_decorations(prefix: Path, enabled: bool, run=subprocess.run):
    res = _wine(decorations_argv(enabled)[1:], prefix, run=run)
    if res.returncode != 0:
        raise RuntimeError((res.stderr or res.stdout).strip() or "wine reg add failed")
