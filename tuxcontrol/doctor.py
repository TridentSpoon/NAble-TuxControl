"""One pass over the machine that both front ends render.

Deliberately read-only: nothing here installs, registers or creates anything
(including Wine prefixes -- see wine.py).
"""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import deps as deps_mod
from . import distro as distro_mod
from . import inspect, protocol, state, wine
from .bundles import KINDS


@dataclass
class Check:
    title: str
    status: str          # ok | warn | fail | info
    detail: str = ""
    fix: str = ""


@dataclass
class Report:
    distro: distro_mod.Distro
    checks: list = field(default_factory=list)
    deps: list = field(default_factory=list)            # [(Dependency, present)]
    wine_version: str = None
    prefixes: list = field(default_factory=list)        # [Path] that exist
    entries: dict = field(default_factory=dict)         # {Path: [(guid, name)]}
    handlers: list = field(default_factory=list)        # [HandlerEntry]
    schemes: dict = field(default_factory=dict)         # {scheme: default desktop id | None}
    decorations: object = None                          # True/False/None
    installed: dict = field(default_factory=dict)       # from state.json

    @property
    def missing_required(self) -> list:
        return [d for d, ok in self.deps if d.required and not ok]

    @property
    def all_entries(self) -> list:
        return [(p, g, n) for p, lst in self.entries.items() for g, n in lst]


def session_check(env=None) -> Check:
    env = os.environ if env is None else env
    kind = (env.get("XDG_SESSION_TYPE") or "").lower()
    if kind == "wayland":
        if env.get("DISPLAY"):
            return Check("Display session", "ok",
                         "Wayland, with XWayland available for Wine windows")
        return Check("Display session", "fail",
                     "Wayland without XWayland \u2014 Wine windows can't open",
                     "Enable/install XWayland for your desktop (e.g. xorg-xwayland on Arch).")
    if kind == "x11":
        return Check("Display session", "ok", "X11")
    if env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"):
        return Check("Display session", "info", "Graphical session (type not reported)")
    return Check("Display session", "warn", "No graphical session detected",
                 "Run TuxControl from your desktop session, not over plain SSH.")


def staged_reports() -> list:
    """Analyze scripts of every bundle we've recorded as installed."""
    reports = []
    for kind, rec in state.load().items():
        root = Path(rec.get("bundle", ""))
        if kind not in KINDS or not root.is_dir():
            continue
        for script in root.rglob("*.sh"):
            try:
                reports.append(inspect.analyze_file(script))
            except OSError:
                pass
    return reports


def run(distro=None, which=shutil.which, query_wine=True) -> Report:
    d = distro or distro_mod.detect()
    rep = Report(distro=d, installed=state.load())

    rep.checks.append(Check("Distribution", "ok" if d.support_level != "adapted" else "info",
                            f"{d.name} \u2014 {d.describe_support()}"))
    rep.checks.append(session_check())

    rep.deps = [(dep, dep.present(which)) for dep in deps_mod.DEPENDENCIES]
    if rep.missing_required:
        names = ", ".join(x.label for x in rep.missing_required)
        rep.checks.append(Check("Dependencies", "fail", f"Missing: {names}",
                                "Install missing dependencies before installing Take Control."))
    else:
        rep.checks.append(Check("Dependencies", "ok", "Everything required is installed"))

    rep.wine_version = deps_mod.wine_version_string() if which("wine") else None
    if rep.wine_version:
        rep.checks.append(Check("Wine", "ok", rep.wine_version))

    if d.family == "arch":
        ml = deps_mod.multilib_enabled()
        if ml is False:
            rep.checks.append(Check(
                "multilib repo", "info", "Disabled",
                "Current Arch Wine (WoW64) doesn't need it; older/third-party builds may."))

    # Known prefixes: default + any named in scripts we've staged.
    reports = staged_reports()
    candidates = [wine.default_prefix()]
    for r in reports:
        candidates += [wine.expand_prefix(p) for p in r.prefixes]
    for p in dict.fromkeys(candidates):
        if wine.prefix_exists(p):
            rep.prefixes.append(p)

    if query_wine and which("wine"):
        for p in rep.prefixes:
            try:
                found = wine.take_control_entries(wine.list_uninstallers(p))
            except (OSError, subprocess.SubprocessError):
                found = []
            if found:
                rep.entries[p] = found
        if rep.prefixes:
            try:
                rep.decorations = wine.decorations_enabled(rep.prefixes[0])
            except (OSError, subprocess.SubprocessError):
                rep.decorations = None

    if rep.all_entries:
        rep.checks.append(Check("Take Control in Wine", "ok",
                                "; ".join(sorted({n for _, _, n in rep.all_entries}))))
    else:
        rep.checks.append(Check("Take Control in Wine", "info", "Nothing installed yet"))

    rep.handlers = protocol.find_handlers()
    schemes = set()
    for r in reports:
        schemes |= r.schemes
    for h in rep.handlers:
        schemes |= set(h.schemes)
    for s in sorted(schemes):
        rep.schemes[s] = protocol.query_default(s)
    viewer_installed = any(k in rep.installed for k in ("ncentral", "nsight"))
    if rep.schemes:
        handler_ids = {h.desktop_id for h in rep.handlers}
        bad = [s for s, cur in rep.schemes.items() if cur not in handler_ids]
        if bad:
            rep.checks.append(Check(
                "Browser links", "warn",
                "Not pointing at Take Control: " + ", ".join(bad),
                "Use 'Repair browser links' (or re-run protocolRegister.sh)."))
        else:
            rep.checks.append(Check("Browser links", "ok",
                                    ", ".join(f"{s}://" for s in rep.schemes)))
    elif viewer_installed:
        rep.checks.append(Check(
            "Browser links", "warn", "No Take Control link handler found",
            "Run the Viewer's protocolRegister.sh (TuxControl offers this after install)."))
    return rep
