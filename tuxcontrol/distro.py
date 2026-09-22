"""Work out which distro we're on, and how far off N-able's tested path it is.

N-able's Linux Console and Viewer installers are shell scripts written with
Ubuntu (20/22) and Fedora (36) in mind. Everything else "should work if the
latest Wine runs there" -- which in practice means the dependency steps inside
those scripts may call a package manager your system doesn't have. The family
detected here decides which package manager *we* use to satisfy dependencies
before the vendor script runs.
"""

from dataclasses import dataclass, field
from pathlib import Path

# Map os-release IDs to a package-manager family. ID_LIKE is consulted too,
# so derivatives we haven't listed (most of them) still land correctly.
_FAMILY_BY_ID = {
    "arch": "arch", "cachyos": "arch", "manjaro": "arch", "endeavouros": "arch",
    "garuda": "arch", "artix": "arch", "archarm": "arch",
    "debian": "debian", "ubuntu": "debian", "linuxmint": "debian", "pop": "debian",
    "elementary": "debian", "zorin": "debian", "kali": "debian", "neon": "debian",
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora", "rocky": "fedora",
    "almalinux": "fedora", "nobara": "fedora", "ultramarine": "fedora",
    "opensuse": "suse", "opensuse-tumbleweed": "suse", "opensuse-leap": "suse",
    "sles": "suse", "suse": "suse",
}

FAMILY_LABELS = {
    "arch": "Arch-based (pacman)",
    "debian": "Debian/Ubuntu-based (apt)",
    "fedora": "Fedora/RHEL-based (dnf)",
    "suse": "openSUSE/SLES (zypper)",
    "unknown": "Unknown package manager",
}

# The combinations N-able's docs name as tested.
_TESTED = {("ubuntu", "20.04"), ("ubuntu", "22.04"), ("fedora", "36")}


def parse_os_release(text: str) -> dict:
    """Parse os-release(5) syntax: KEY=value, value optionally quoted."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
            # os-release allows backslash escapes inside double quotes
            value = (value.replace('\\"', '"').replace("\\$", "$")
                     .replace("\\`", "`").replace("\\\\", "\\"))
        out[key.strip()] = value
    return out


@dataclass
class Distro:
    id: str = "linux"
    name: str = "Linux"
    version_id: str = ""
    like: tuple = field(default_factory=tuple)

    @property
    def family(self) -> str:
        for candidate in (self.id, *self.like):
            fam = _FAMILY_BY_ID.get(candidate)
            if fam:
                return fam
        return "unknown"

    @property
    def family_label(self) -> str:
        return FAMILY_LABELS[self.family]

    @property
    def support_level(self) -> str:
        """'tested', 'family' or 'adapted'.

        tested  -- exactly what N-able lists as tested.
        family  -- apt/dnf family: the vendor scripts' package steps should
                   work, but this release wasn't what N-able tested.
        adapted -- pacman/zypper/unknown: TuxControl has to satisfy the
                   dependencies itself so the vendor scripts skip their own
                   (foreign) package-manager steps.
        """
        major_minor = self.version_id
        if (self.id, major_minor) in _TESTED:
            return "tested"
        if self.family in ("debian", "fedora"):
            return "family"
        return "adapted"

    def describe_support(self) -> str:
        level = self.support_level
        if level == "tested":
            return "Tested by N-able"
        if level == "family":
            return "Same family as N-able's tested distros"
        return "Not covered by N-able's scripts \u2014 TuxControl handles dependencies"


def detect(path: str = "/etc/os-release") -> Distro:
    for candidate in (path, "/usr/lib/os-release"):
        try:
            data = parse_os_release(Path(candidate).read_text(encoding="utf-8"))
            break
        except OSError:
            continue
    else:
        return Distro()
    return Distro(
        id=data.get("ID", "linux").lower(),
        name=data.get("PRETTY_NAME") or data.get("NAME", "Linux"),
        version_id=data.get("VERSION_ID", ""),
        like=tuple(data.get("ID_LIKE", "").lower().split()),
    )
