"""Read N-able's shell scripts before running them, and say what they'll do.

This is a heuristic reader, not a shell parser. Its job is to answer the
questions an admin actually has before running a vendor script on a distro
the vendor didn't test:

* Does it call a package manager this system doesn't have?
* Does it need root (sudo/pkexec)?
* Does it remove Wine system-wide? (uninstallConsole.sh does, per N-able.)
* Which browser link schemes does it register, and which Wine prefix does it use?
* What does it download, and from where?

Everything it reports is also visible by reading the script -- TuxControl
shows the full text alongside the findings.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

PACKAGE_MANAGERS = {
    "apt": re.compile(r"(?<![\w-])(apt-get|apt|dpkg|add-apt-repository|apt-key)(?![\w-])"),
    "dnf": re.compile(r"(?<![\w-])(dnf|yum|rpm)(?![\w-])"),
    "pacman": re.compile(r"(?<![\w-])(pacman|yay|paru)(?![\w-])"),
    "zypper": re.compile(r"(?<![\w-])zypper(?![\w-])"),
}
FAMILY_PM = {"debian": "apt", "fedora": "dnf", "arch": "pacman", "suse": "zypper"}

_SUDO = re.compile(r"(?<![\w-])(sudo|pkexec|doas)(?![\w-])|(?<![\w-])su\s+-c\b")
_SCHEME = re.compile(r"x-scheme-handler/([A-Za-z][A-Za-z0-9+.-]*)")
_PAYLOAD = re.compile(r"[\w./${}~-]*?([\w.-]+\.(?:exe|msi))\b", re.IGNORECASE)
_URL = re.compile(r"https?://[^\s\"'<>)]+")
_PREFIX = re.compile(r"WINEPREFIX=([\"']?)([^\s\"';]+)\1")
_READ = re.compile(r"(?<![\w-])read(?![\w-])")
_WINE_REMOVE = re.compile(
    r"(remove|purge|autoremove|erase|-R\w*)\b[^\n]*\bwine|\bwine[^\n]*\b(remove|purge)\b",
    re.IGNORECASE)
_SYSTEM_PATHS = re.compile(r"(?<![\w.$~])(/usr/[\w/.-]+|/etc/[\w/.-]+|/opt/[\w/.-]+)")


def strip_comments(text: str) -> str:
    """Drop full-line comments (incl. shebang). Inline '#' is kept -- too
    easy to confuse with ${#var} or URLs to strip safely."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


@dataclass
class Finding:
    level: str      # "info" | "warn" | "danger"
    message: str


@dataclass
class ScriptReport:
    path: str
    package_managers: set = field(default_factory=set)
    uses_root: bool = False
    interactive: bool = False
    removes_wine: bool = False
    schemes: set = field(default_factory=set)
    payloads: set = field(default_factory=set)
    downloads: list = field(default_factory=list)
    prefixes: set = field(default_factory=set)
    system_paths: set = field(default_factory=set)

    @property
    def name(self) -> str:
        return Path(self.path).name


def analyze_text(text: str, path: str = "<script>") -> ScriptReport:
    body = strip_comments(text)
    r = ScriptReport(path=path)
    for pm, rx in PACKAGE_MANAGERS.items():
        if rx.search(body):
            r.package_managers.add(pm)
    r.uses_root = bool(_SUDO.search(body))
    r.interactive = bool(_READ.search(body))
    r.removes_wine = bool(_WINE_REMOVE.search(body))
    r.schemes = set(_SCHEME.findall(body))
    r.payloads = {m.group(1) for m in _PAYLOAD.finditer(body)}
    r.downloads = list(dict.fromkeys(_URL.findall(body)))
    r.prefixes = {m.group(2) for m in _PREFIX.finditer(body)}
    r.system_paths = set(_SYSTEM_PATHS.findall(body)) - {"/usr/bin/env"}
    return r


def analyze_file(path) -> ScriptReport:
    p = Path(path)
    return analyze_text(p.read_text(encoding="utf-8", errors="replace"), str(p))


def findings(report: ScriptReport, family: str, wine_present: bool) -> list:
    """Turn a report into admin-facing findings for this machine."""
    out = []
    native = FAMILY_PM.get(family)
    foreign = sorted(pm for pm in report.package_managers if pm != native)
    if foreign:
        if wine_present:
            out.append(Finding(
                "info",
                f"Calls {', '.join(foreign)}, which this system doesn't use. Wine is "
                "already installed, so the script should skip its own Wine install; "
                "if it still fails at a package step, install that package with "
                "your own package manager and re-run."))
        else:
            out.append(Finding(
                "warn",
                f"Calls {', '.join(foreign)}, which this system doesn't use. Install "
                "Wine with TuxControl first so the script skips that step."))
    if report.removes_wine:
        out.append(Finding(
            "danger",
            "Removes Wine system-wide. Anything else you run under Wine loses it too. "
            "To remove only Take Control, use its Windows uninstaller instead."))
    if report.uses_root:
        out.append(Finding(
            "info", "Asks for root (sudo/pkexec) itself \u2014 expect a password prompt in the terminal."))
    if report.interactive:
        out.append(Finding("info", "Interactive: it asks questions you answer in the terminal."))
    if report.schemes:
        out.append(Finding(
            "info", "Registers browser link scheme(s): " + ", ".join(sorted(report.schemes))))
    if report.prefixes:
        out.append(Finding("info", "Uses Wine prefix: " + ", ".join(sorted(report.prefixes))))
    if report.downloads:
        out.append(Finding("info", "Downloads from: " + ", ".join(report.downloads[:5])
                           + (" \u2026" if len(report.downloads) > 5 else "")))
    if report.system_paths:
        shown = sorted(report.system_paths)[:5]
        out.append(Finding("info", "Touches system paths: " + ", ".join(shown)
                           + (" \u2026" if len(report.system_paths) > 5 else "")))
    return out
