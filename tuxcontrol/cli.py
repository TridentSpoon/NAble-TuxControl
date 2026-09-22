"""Text front end. Every action is a subcommand (scriptable) and the same
actions are reachable from a menu when run with no arguments.

Runs unprivileged. Only distro package installs go through sudo, and the
exact command is shown first.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import APP_NAME, VERSION, bundles, deps, doctor, inspect, privileged, protocol, state, update, wine
from .distro import detect

ICON = {"ok": "\u2714", "warn": "\u26a0", "fail": "\u2716", "info": "\u2139",
        "danger": "\u2716"}


# ----------------------------------------------------------------- prompts

def ask(question: str, default: bool = False) -> bool:
    hint = "[Y/n]" if default else "[y/N]"
    try:
        ans = input(f"{question} {hint} ").strip().lower()
    except EOFError:
        return default
    return default if not ans else ans in ("y", "yes")


def choose(title: str, options: list):
    """options: [(label, value)]; returns value or None."""
    print(f"\n{title}")
    for i, (label, _) in enumerate(options, 1):
        print(f"  {i}) {label}")
    try:
        raw = input("Choose (Enter to cancel): ").strip()
    except EOFError:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1][1]
    return None


# ----------------------------------------------------------------- actions

def cmd_doctor(args=None) -> int:
    rep = doctor.run()
    print(f"\n{APP_NAME} {VERSION} \u2014 machine check\n")
    for c in rep.checks:
        print(f" {ICON[c.status]} {c.title}: {c.detail}")
        if c.fix:
            print(f"     \u2192 {c.fix}")
    print("\nDependencies:")
    for d, ok in rep.deps:
        tag = "required" if d.required else "optional"
        print(f" {ICON['ok'] if ok else (ICON['fail'] if d.required else ICON['info'])} "
              f"{d.label} ({tag})")
    if rep.installed:
        print("\nInstalled with TuxControl:")
        for k, rec in rep.installed.items():
            label = bundles.KINDS[k].label if k in bundles.KINDS else k
            print(f"   {label} \u2014 {rec.get('installed_at', '?')}")
    if rep.decorations is not None:
        print(f"\nWine window decorations: {'on' if rep.decorations else 'off'}")
    return 1 if any(c.status == "fail" for c in rep.checks) else 0


def cmd_deps(args=None, include_optional=False) -> int:
    d = detect()
    if args is not None:
        include_optional = getattr(args, "optional", False)
    todo = deps.missing(include_optional=include_optional)
    if not todo:
        print("All dependencies are already installed.")
        return 0
    print("Missing: " + ", ".join(x.label for x in todo))
    try:
        argv = deps.install_command(d.family, deps.packages_for(todo, d.family))
    except ValueError:
        print(f"TuxControl doesn't know the package manager on {d.name}. Install these "
              "yourself: " + ", ".join(x.label for x in todo))
        return 1
    print(f"\nThis will run as root:\n  {privileged.describe(argv)}\n")
    if not ask("Go ahead?", True):
        return 1
    try:
        res = privileged.run_sudo(argv)
    except privileged.PrivilegeError as e:
        print(f"Couldn't escalate: {e}")
        return 1
    if res.returncode != 0:
        print(f"The package manager exited with {res.returncode}.")
        return res.returncode
    still = deps.missing(include_optional=include_optional)
    if still:
        print("Installed, but still not found on PATH: " + ", ".join(x.label for x in still))
        return 1
    print("Done.")
    return 0


def print_findings(staged, family: str):
    wine_ok = deps.by_key("wine").present()
    print(f"\nBundle: {staged.kind.label}")
    print(f"  SHA-256: {staged.sha256}")
    print(f"  Staged at: {staged.root}")
    for script in staged.scripts():
        rep = inspect.analyze_file(script)
        fs = inspect.findings(rep, family, wine_ok)
        print(f"\n  {script.relative_to(staged.root)}")
        if not fs:
            print("    (nothing notable)")
        for f in fs:
            print(f"    {ICON[f.level]} {f.message}")


def cmd_inspect(args) -> int:
    try:
        staged = bundles.stage(args.zip)
    except bundles.BundleError as e:
        print(f"Can't use that zip: {e}")
        return 1
    print_findings(staged, detect().family)
    print("\nNothing has been run. Read the scripts under the staged folder if you "
          "want the full detail.")
    return 0


def obtain_zip(kind: bundles.BundleKind, zip_arg, version: str):
    if zip_arg:
        return Path(zip_arg)
    if not kind.downloadable:
        print(f"{kind.zip_name} has to be downloaded from the {kind.where_to_get}.\n"
              f"Then run: tuxcontrol install {kind.key} --zip /path/to/{kind.zip_name}")
        return None
    url = kind.url(version)
    dest = bundles.staging_root() / "downloads" / version / kind.zip_name
    print(f"Download {kind.zip_name} {version} from:\n  {url}")
    if not ask("Download it now?", True):
        return None

    def progress(done, total):
        if total:
            print(f"\r  {done * 100 // total:3d}% of {total // 1024} KiB", end="", flush=True)
    try:
        bundles.download(url, dest, progress)
    except Exception as e:  # noqa: BLE001
        print(f"\nDownload failed: {e}")
        return None
    print()
    return dest


def run_script(script: Path) -> int:
    print(f"\n--- running {script.name} (answer its questions below) ---\n")
    try:
        return subprocess.run(["bash", str(script)], cwd=script.parent).returncode
    except KeyboardInterrupt:
        return 130


def cmd_install(args) -> int:
    kind = bundles.KINDS[args.kind]
    d = detect()
    if deps.missing():
        print("Required dependencies are missing; TuxControl installs them first so "
              "N-able's script doesn't try its own (possibly foreign) package manager.")
        if cmd_deps(include_optional=False) != 0 and not ask("Continue anyway?", False):
            return 1
    zip_path = obtain_zip(kind, args.zip, args.viewer_version)
    if not zip_path:
        return 1
    try:
        staged = bundles.stage(zip_path, expected_kind=kind.key)
    except bundles.BundleError as e:
        print(f"Can't use that zip: {e}")
        return 1
    print_findings(staged, d.family)
    script = staged.install_script
    if not script:
        print(f"\n{kind.install_script} is missing from the bundle.")
        return 1
    if not args.yes and not ask(f"\nRun {script.name} now?", True):
        return 1
    rc = run_script(script)
    if rc != 0:
        print(f"\n{script.name} exited with {rc}. Nothing was recorded; fix the error and re-run.")
        return rc
    state.record_install(kind.key, staged)
    print(f"\n{kind.label} installed.")
    if kind.protocol_script and staged.protocol_script:
        if args.yes or ask("Register the browser link handler now (protocolRegister.sh)?", True):
            rc = run_script(staged.protocol_script)
            if rc != 0:
                print(f"protocolRegister.sh exited with {rc}.")
    print("\nTip: if Wine windows lose their title bars or buttons, run "
          "`tuxcontrol decorations off` (or `on`) and relaunch.")
    return 0


def cmd_register(args) -> int:
    rec = state.load().get(args.kind)
    if not rec:
        print("That viewer isn't installed with TuxControl yet.")
        return 1
    script = bundles.find_script(Path(rec["bundle"]), bundles.KINDS[args.kind].protocol_script)
    if not script:
        print("protocolRegister.sh isn't in the staged bundle.")
        return 1
    return run_script(script)


def cmd_repair_links(args=None) -> int:
    rep = doctor.run(query_wine=False)
    if not rep.schemes:
        print("No Take Control link schemes found. Install a Viewer first.")
        return 1
    ids = {h.desktop_id: h for h in rep.handlers}
    changed = 0
    for scheme, current in rep.schemes.items():
        candidates = [h for h in rep.handlers if scheme in h.schemes]
        if current in ids:
            print(f"{ICON['ok']} {scheme}:// \u2192 {current}")
            continue
        if not candidates:
            print(f"{ICON['warn']} {scheme}:// \u2014 no Take Control entry claims it; "
                  "re-run protocolRegister.sh")
            continue
        target = candidates[0] if len(candidates) == 1 else choose(
            f"Which entry should open {scheme}:// links?",
            [(f"{h.name} ({h.desktop_id})", h) for h in candidates])
        if not target:
            continue
        protocol.set_default(scheme, target.desktop_id)
        print(f"{ICON['ok']} {scheme}:// \u2192 {target.desktop_id} (was {current or 'unset'})")
        changed += 1
    return 0


def cmd_decorations(args) -> int:
    prefix = wine.default_prefix()
    if not wine.prefix_exists(prefix):
        print(f"No Wine prefix at {prefix}; install Take Control first.")
        return 1
    if args.mode == "status":
        print("on" if wine.decorations_enabled(prefix) else "off")
        return 0
    wine.set_decorations(prefix, args.mode == "on")
    print(f"Window-manager decorations {args.mode}. Restart the Console/Viewer to see it.")
    return 0


def cmd_uninstall(args) -> int:
    kind = bundles.KINDS[args.kind]
    rep = doctor.run()
    options = [(f"Windows uninstaller: {n}  [{p}]", ("entry", p, g))
               for p, g, n in rep.all_entries]
    rec = rep.installed.get(kind.key)
    vendor = bundles.find_script(Path(rec["bundle"]), kind.uninstall_script) if rec else None
    if vendor:
        options.append((f"N-able's {vendor.name}", ("vendor", vendor, None)))
    if not options:
        print("Nothing to uninstall was found.")
        return 1
    pick = choose(f"How should {kind.label} be removed?", options)
    if not pick:
        return 1
    how, target, guid = pick
    if how == "entry":
        env_prefix = {"WINEPREFIX": str(target)}
        print(f"Starting the Windows uninstaller in {target}\u2026")
        rc = subprocess.run(wine.uninstall_argv(guid),
                            env={**os.environ, **env_prefix}).returncode
    else:
        r = inspect.analyze_file(target)
        for f in inspect.findings(r, detect().family, True):
            print(f" {ICON[f.level]} {f.message}")
        if r.removes_wine:
            try:
                typed = input("\nThis removes Wine for every app. Type 'remove wine' to continue: ")
            except EOFError:
                typed = ""
            if typed.strip().lower() != "remove wine":
                print("Cancelled.")
                return 1
        elif not ask(f"Run {target.name}?", False):
            return 1
        rc = run_script(target)
    if rc == 0:
        state.forget(kind.key)
        print("Done.")
    else:
        print(f"Exited with {rc}.")
    return rc


def cmd_updates(args=None) -> int:
    app = update.newer_app_release()
    viewer = update.newer_viewer()
    if app:
        print(f"TuxControl {app[0]} is available: {app[1]}")
    if viewer:
        print(f"N-able has announced Linux Viewer {viewer}; install it with "
              f"`tuxcontrol install ncentral --viewer-version {viewer}` (or nsight).")
    if not app and not viewer:
        print("No updates found (or you're offline).")
    return 0


# ----------------------------------------------------------------- menu

def menu() -> int:
    while True:
        action = choose(f"{APP_NAME} {VERSION}", [
            ("Check this machine (doctor)", "doctor"),
            ("Install missing dependencies", "deps"),
            ("Install the Technician Console", "console"),
            ("Install the N-central Viewer", "ncentral"),
            ("Install the N-sight Viewer", "nsight"),
            ("Repair browser links", "links"),
            ("Toggle Wine window decorations", "decor"),
            ("Uninstall something", "uninstall"),
            ("Check for updates", "updates"),
            ("Quit", "quit"),
        ])
        if action in (None, "quit"):
            return 0
        if action == "doctor":
            cmd_doctor()
        elif action == "deps":
            cmd_deps(include_optional=ask("Include optional extras (curl, winetricks)?"))
        elif action in bundles.KINDS:
            zp = None
            if action == "console" or not ask("Download it from N-able?", True):
                try:
                    zp = input("Path to the zip: ").strip() or None
                except EOFError:
                    zp = None
                if not zp:
                    continue
            cmd_install(argparse.Namespace(kind=action, zip=zp, yes=False,
                                           viewer_version=bundles.VIEWER_VERSION))
        elif action == "links":
            cmd_repair_links()
        elif action == "decor":
            prefix = wine.default_prefix()
            if not wine.prefix_exists(prefix):
                print("No Wine prefix yet.")
                continue
            on = wine.decorations_enabled(prefix)
            if ask(f"Decorations are {'on' if on else 'off'}. Switch them {'off' if on else 'on'}?", True):
                cmd_decorations(argparse.Namespace(mode="off" if on else "on"))
        elif action == "uninstall":
            k = choose("Uninstall which?", [(v.label, k) for k, v in bundles.KINDS.items()])
            if k:
                cmd_uninstall(argparse.Namespace(kind=k))
        elif action == "updates":
            cmd_updates()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tuxcontrol",
                                description="Install N-able Take Control on any Linux distro.")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("doctor", help="check this machine (read-only)")
    dp = sub.add_parser("deps", help="install missing dependencies")
    dp.add_argument("--optional", action="store_true", help="include curl and winetricks")
    ip = sub.add_parser("inspect", help="stage a zip and report what its scripts do; runs nothing")
    ip.add_argument("zip")
    inst = sub.add_parser("install", help="install a component")
    inst.add_argument("kind", choices=list(bundles.KINDS))
    inst.add_argument("--zip", help="use this zip instead of downloading")
    inst.add_argument("--viewer-version", default=bundles.VIEWER_VERSION)
    inst.add_argument("-y", "--yes", action="store_true", help="don't ask before running scripts")
    rp = sub.add_parser("register", help="re-run a viewer's protocolRegister.sh")
    rp.add_argument("kind", choices=["ncentral", "nsight"])
    sub.add_parser("repair-links", help="point Take Control URL schemes back at Take Control")
    dec = sub.add_parser("decorations", help="Wine window-manager decorations")
    dec.add_argument("mode", choices=["on", "off", "status"])
    up = sub.add_parser("uninstall", help="remove a component")
    up.add_argument("kind", choices=list(bundles.KINDS))
    sub.add_parser("updates", help="check for TuxControl and Viewer updates")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "doctor": cmd_doctor, "deps": cmd_deps, "inspect": cmd_inspect,
        "install": cmd_install, "register": cmd_register,
        "repair-links": cmd_repair_links, "decorations": cmd_decorations,
        "uninstall": cmd_uninstall, "updates": cmd_updates,
    }
    try:
        if not args.cmd:
            return menu()
        return handlers[args.cmd](args)
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
