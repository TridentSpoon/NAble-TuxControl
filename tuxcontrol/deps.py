"""What Take Control needs on the host, and how to get it on each distro.

The key trick for non-Debian systems: N-able's install scripts offer to install
Wine themselves (via their own package-manager calls) *only if Wine is
missing*. With Wine already present they take a different path. So installing
Wine natively first, with the right package manager, is what lets the vendor
scripts run on Arch/CachyOS, openSUSE and friends.
"""

import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Dependency:
    key: str
    label: str
    binaries: tuple      # any one of these on PATH satisfies it
    packages: dict       # family -> tuple of package names
    required: bool
    why: str

    def present(self, which=shutil.which) -> bool:
        return any(which(b) for b in self.binaries)

    def packages_for(self, family: str) -> tuple:
        return tuple(self.packages.get(family, ()))


DEPENDENCIES = (
    Dependency(
        "wine", "Wine", ("wine",),
        {"arch": ("wine",), "debian": ("wine",), "fedora": ("wine",), "suse": ("wine",),
         "void": ("wine",), "solus": ("wine",), "alpine": ("wine",)},
        True,
        "The Console and Viewer are Windows programs running under Wine.",
    ),
    Dependency(
        "gpg", "GnuPG", ("gpg", "gpg2"),
        {"arch": ("gnupg",), "debian": ("gpg",), "fedora": ("gnupg2",), "suse": ("gpg2",),
         "void": ("gnupg",), "solus": ("gnupg",), "alpine": ("gnupg",)},
        True,
        "N-able's scripts require gpg (it replaced gpgv2 in their 2025 update).",
    ),
    Dependency(
        "xdg", "xdg-utils", ("xdg-mime",),
        {"arch": ("xdg-utils",), "debian": ("xdg-utils",), "fedora": ("xdg-utils",),
         "suse": ("xdg-utils",), "void": ("xdg-utils",), "solus": ("xdg-utils",),
         "alpine": ("xdg-utils",)},
        True,
        "Registers the browser link handler so N-central/N-sight can launch the Viewer.",
    ),
    Dependency(
        "curl", "curl", ("curl", "wget"),
        {"arch": ("curl",), "debian": ("curl",), "fedora": ("curl",), "suse": ("curl",),
         "void": ("curl",), "solus": ("curl",), "alpine": ("curl",)},
        False,
        "Installer scripts commonly download components with curl or wget.",
    ),
    Dependency(
        "winetricks", "winetricks", ("winetricks",),
        {"arch": ("winetricks",), "debian": ("winetricks",), "fedora": ("winetricks",),
         "suse": ("winetricks",), "void": ("winetricks",), "solus": ("winetricks",),
         "alpine": ("winetricks",)},
        False,
        "Handy for fixing fonts or runtimes inside the Wine prefix. Optional.",
    ),
)


def by_key(key: str) -> Dependency:
    for d in DEPENDENCIES:
        if d.key == key:
            return d
    raise KeyError(key)


def missing(which=shutil.which, include_optional=False) -> list:
    return [d for d in DEPENDENCIES
            if (d.required or include_optional) and not d.present(which)]


def install_command(family: str, packages) -> list:
    """argv (to run as root) installing ``packages`` on ``family``.

    Raises ValueError for an unknown family -- better to say "install these
    yourself" than to guess at a package manager.
    """
    pkgs = list(dict.fromkeys(packages))  # de-dupe, keep order
    if not pkgs:
        raise ValueError("nothing to install")
    if family == "arch":
        return ["pacman", "-S", "--needed", "--noconfirm", *pkgs]
    if family == "debian":
        joined = " ".join(shlex.quote(p) for p in pkgs)
        # Wine on Debian/Ubuntu requires 32-bit userspace; enable it first.
        if "wine" in pkgs:
            return ["sh", "-c",
                    f"dpkg --add-architecture i386 && apt-get update && apt-get install -y {joined}"]
        return ["sh", "-c", f"apt-get update && apt-get install -y {joined}"]
    if family == "fedora":
        return ["dnf", "install", "-y", *pkgs]
    if family == "suse":
        return ["zypper", "--non-interactive", "install", *pkgs]
    if family == "void":
        return ["xbps-install", "-Sy", *pkgs]
    if family == "solus":
        return ["eopkg", "install", "-y", *pkgs]
    if family == "alpine":
        return ["apk", "add", "--no-cache", *pkgs]
    raise ValueError(f"no package manager known for family {family!r}")


def packages_for(deps, family: str) -> list:
    out = []
    for d in deps:
        out.extend(d.packages_for(family))
    return out


# ---------------------------------------------------------------- Wine details

_WINE_VER = re.compile(r"wine-(\d+)\.(\d+)(?:\.(\d+))?")


def parse_wine_version(text: str):
    """'wine-9.21 (Staging)' -> (9, 21, 0); None if unparseable."""
    m = _WINE_VER.search(text or "")
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def wine_version_string(run=subprocess.run):
    if not shutil.which("wine"):
        return None
    try:
        res = run(["wine", "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (res.stdout or res.stderr).strip() or None


def multilib_enabled(pacman_conf: str = "/etc/pacman.conf"):
    """True/False for Arch-family systems, None if there's no pacman.conf.

    Only informational: current Arch Wine builds use WoW64 and no longer need
    multilib, but older or third-party builds may.
    """
    try:
        text = Path(pacman_conf).read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_multilib(text)


def parse_multilib(text: str) -> bool:
    return any(line.strip() == "[multilib]" for line in text.splitlines())
