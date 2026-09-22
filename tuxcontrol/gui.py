"""GTK4/libadwaita front end.

One window, laid out top to bottom in the order you'd actually work:
machine check -> dependencies -> Take Control components -> browser links ->
Wine tweaks. Everything slow (Wine queries, downloads, pkexec) runs on a
background thread so the window stays responsive.

The window launches unprivileged. The only root step -- installing distro
packages -- goes through pkexec, with the exact command shown first.
N-able's own scripts run in your terminal emulator, because they ask
questions and may call sudo themselves.
"""

import argparse
import os
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from . import (APP_ID, APP_NAME, REPO_URL, VERSION, bundles, deps, doctor,  # noqa: E402
               inspect, privileged, protocol, state, terminal, update, wine)
from .distro import detect  # noqa: E402

STATUS_ICON = {
    "ok": "emblem-ok-symbolic",
    "warn": "dialog-warning-symbolic",
    "fail": "dialog-error-symbolic",
    "info": "dialog-information-symbolic",
    "danger": "dialog-error-symbolic",
}
STATUS_CSS = {"ok": "success", "warn": "warning", "fail": "error", "danger": "error"}


def status_icon(status: str) -> Gtk.Image:
    img = Gtk.Image.new_from_icon_name(STATUS_ICON[status])
    css = STATUS_CSS.get(status)
    if css:
        img.add_css_class(css)
    return img


def row(title: str, subtitle: str = "", status: str = None) -> Adw.ActionRow:
    r = Adw.ActionRow(title=title, subtitle=subtitle)
    r.set_use_markup(False)          # titles come from files/scripts; never parse them
    r.set_subtitle_lines(0)
    if status:
        r.add_prefix(status_icon(status))
    return r


def pill(label: str, css: str = None, cb=None) -> Gtk.Button:
    b = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
    if css:
        b.add_css_class(css)
    if cb:
        b.connect("clicked", lambda *_: cb())
    return b


def wrap_label(text: str, css: str = None) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True)
    lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    if css:
        lbl.add_css_class(css)
    return lbl


class Window(Adw.ApplicationWindow):
    def __init__(self, app, check_updates=True):
        super().__init__(application=app, title=APP_NAME,
                         default_width=780, default_height=840)
        self.distro = detect()
        self.report = None
        self.groups = []
        self._busy_count = 0
        self._rendering = False

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        refresh = Gtk.Button(icon_name="view-refresh-symbolic",
                             tooltip_text="Re-check this machine")
        refresh.connect("clicked", lambda *_: self.refresh())
        header.pack_start(refresh)
        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner)

        menu = Gio.Menu()
        menu.append("Inspect a zip\u2026", "win.inspect")
        menu.append("Repair browser links", "win.repair-links")
        menu.append("Check for updates", "win.check-updates")
        menu.append(f"About {APP_NAME}", "win.about")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       tooltip_text="Menu"))
        view.add_top_bar(header)

        self.toasts = Adw.ToastOverlay()
        self.page = Adw.PreferencesPage()
        self.toasts.set_child(self.page)
        view.set_content(self.toasts)
        self.set_content(view)

        for name, cb in (("inspect", self.on_inspect), ("repair-links", self.repair_links),
                         ("check-updates", lambda: self.check_updates(manual=True)),
                         ("about", self.on_about)):
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", lambda _a, _p, cb=cb: cb())
            self.add_action(act)

        self.refresh()
        if check_updates:
            GLib.timeout_add_seconds(3, lambda: (self.check_updates(manual=False), False)[1])

    # ------------------------------------------------------------ plumbing

    def busy(self, on: bool):
        self._busy_count += 1 if on else -1
        active = self._busy_count > 0
        self.spinner.set_spinning(active)
        self.page.set_sensitive(not active)

    def run_async(self, work, done=None, what="Working"):
        self.busy(True)

        def target():
            try:
                result = work()
                GLib.idle_add(self._finish, done, result, None, what)
            except Exception as e:  # noqa: BLE001 -- surfaced to the user
                GLib.idle_add(self._finish, done, None, e, what)
        threading.Thread(target=target, daemon=True).start()

    def _finish(self, done, result, exc, what):
        self.busy(False)
        if exc is not None:
            self.alert(f"{what} failed", str(exc), [("close", "Close")])
        elif done:
            done(result)
        return False

    def toast(self, text: str, button=None, on_button=None):
        t = Adw.Toast.new(text)
        if button and on_button:
            t.set_button_label(button)
            t.connect("button-clicked", lambda *_: on_button())
        self.toasts.add_toast(t)

    def alert(self, heading, body, responses, callback=None, extra=None,
              default=None, destructive=None, markup=False):
        d = Adw.AlertDialog(heading=heading, body=body)
        d.set_body_use_markup(markup)
        for rid, label in responses:
            d.add_response(rid, label)
        d.set_close_response(responses[0][0])
        if default:
            d.set_response_appearance(default, Adw.ResponseAppearance.SUGGESTED)
            d.set_default_response(default)
        if destructive:
            d.set_response_appearance(destructive, Adw.ResponseAppearance.DESTRUCTIVE)
        if extra is not None:
            d.set_extra_child(extra)
        if callback:
            d.connect("response", lambda _d, r: callback(r))
        d.present(self)
        return d

    def open_uri(self, uri: str):
        Gtk.UriLauncher.new(uri).launch(self, None, None)

    # ------------------------------------------------------------ rendering

    def refresh(self):
        self.run_async(lambda: doctor.run(distro=self.distro), self.render, "Checking this machine")

    def render(self, rep):
        self._rendering = True
        self.report = rep
        for g in self.groups:
            self.page.remove(g)
        self.groups = [self._machine_group(rep), self._deps_group(rep),
                       self._components_group(rep)]
        links = self._links_group(rep)
        if links:
            self.groups.append(links)
        self.groups.append(self._tweaks_group(rep))
        for g in self.groups:
            self.page.add(g)
        self._rendering = False

    def _machine_group(self, rep):
        g = Adw.PreferencesGroup(title="This machine")
        for c in rep.checks:
            sub = c.detail + (f"\n\u2192 {c.fix}" if c.fix else "")
            g.add(row(c.title, sub, c.status))
        return g

    def _deps_group(self, rep):
        g = Adw.PreferencesGroup(
            title="Dependencies",
            description="Installed with your own package manager first, so N-able's "
                        "scripts never need to reach for one this system doesn't have.")
        missing_any = any(not ok for d, ok in rep.deps)
        btn = pill("Install missing\u2026", "suggested-action" if rep.missing_required else None,
                   self.install_deps)
        btn.set_sensitive(missing_any)
        g.set_header_suffix(btn)
        for d, ok in rep.deps:
            status = "ok" if ok else ("fail" if d.required else "info")
            r = row(d.label + ("" if d.required else " (optional)"), d.why, status)
            r.add_suffix(Gtk.Label(label="Installed" if ok else "Missing",
                                   css_classes=["dim-label"]))
            g.add(r)
        return g

    def _components_group(self, rep):
        g = Adw.PreferencesGroup(title="Take Control")
        found = sorted({n for _, _, n in rep.all_entries})
        if found:
            g.set_description("Found in Wine: " + "; ".join(found))
        for key, kind in bundles.KINDS.items():
            rec = rep.installed.get(key)
            if rec:
                sub, status = f"Installed with TuxControl on {rec.get('installed_at', '?')}", "ok"
            else:
                sub, status = f"Not installed \u2014 get it from: {kind.where_to_get}", None
            r = row(kind.label, sub, status)
            box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
            box.append(pill("Reinstall\u2026" if rec else "Install\u2026",
                            None if rec else "suggested-action",
                            lambda k=key: self.start_install(k)))
            if rec or found:
                box.append(pill("Uninstall\u2026", "destructive-action",
                                lambda k=key: self.start_uninstall(k)))
            r.add_suffix(box)
            g.add(r)
        return g

    def _links_group(self, rep):
        viewers = any(k in rep.installed for k in ("ncentral", "nsight"))
        if not rep.schemes and not viewers:
            return None
        g = Adw.PreferencesGroup(
            title="Browser links",
            description="Which app opens Remote Control links from N-central / N-sight.")
        g.set_header_suffix(pill("Repair", None, self.repair_links))
        ids = {h.desktop_id for h in rep.handlers}
        if not rep.schemes:
            g.add(row("No link handler registered",
                      "Run the Viewer's protocolRegister.sh (Reinstall offers it).", "warn"))
        for scheme, current in rep.schemes.items():
            ok = current in ids
            g.add(row(f"{scheme}://", f"Opens with: {current or 'nothing'}",
                      "ok" if ok else "warn"))
        return g

    def _tweaks_group(self, rep):
        g = Adw.PreferencesGroup(title="Wine tweaks")
        sw = Adw.SwitchRow(
            title="Let the window manager decorate Wine windows",
            subtitle="If Console/Viewer title bars or minimise/maximise/close buttons "
                     "misbehave, flip this and restart the app. N-able's own advice "
                     "differs between the Console and the Viewer, so try both.")
        sw.set_use_markup(False)
        if rep.decorations is None:
            sw.set_sensitive(False)
            sw.set_subtitle("Available once Take Control is installed (no Wine prefix yet).")
        else:
            sw.set_active(rep.decorations)
        sw.connect("notify::active", self.on_decorations)
        g.add(sw)
        return g

    # ------------------------------------------------------------ dependencies

    def install_deps(self, then=None):
        todo = deps.missing(include_optional=True)
        if not todo:
            if then:
                then()
            return
        try:
            argv = deps.install_command(self.distro.family, deps.packages_for(todo, self.distro.family))
        except ValueError:
            self.alert("Unknown package manager",
                       f"TuxControl doesn't know how to install packages on {self.distro.name}. "
                       "Please install: " + ", ".join(d.label for d in todo),
                       [("close", "Close")])
            return
        cmd = GLib.markup_escape_text(privileged.describe(argv))
        body = ("This runs as root after your password prompt:\n\n"
                f"<tt>{cmd}</tt>")

        def go(resp):
            if resp != "install":
                return

            def work():
                return privileged.run_pkexec(argv)

            def done(res):
                if res.returncode != 0:
                    tail = "\n".join((res.stderr or res.stdout).strip().splitlines()[-12:])
                    self.alert("Package install failed", tail or f"Exit code {res.returncode}",
                               [("close", "Close")])
                else:
                    self.toast("Dependencies installed")
                self.refresh()
                if then and res.returncode == 0:
                    then()
            self.toast("Waiting for authentication\u2026")
            self.run_async(work, done, "Installing dependencies")

        self.alert("Install dependencies?", body, [("cancel", "Cancel"), ("install", "Install")],
                   go, default="install", markup=True)

    # ------------------------------------------------------------ install flow

    def start_install(self, key: str):
        kind = bundles.KINDS[key]
        if deps.missing():
            names = ", ".join(d.label for d in deps.missing())
            self.alert(
                "Install dependencies first?",
                f"{names} {'is' if len(deps.missing()) == 1 else 'are'} missing. Installing "
                "them now means N-able's script won't try its own package manager.",
                [("cancel", "Cancel"), ("skip", "Continue anyway"), ("install", "Install first")],
                lambda r: (self.install_deps(then=lambda: self._choose_source(kind)) if r == "install"
                           else self._choose_source(kind) if r == "skip" else None),
                default="install")
            return
        self._choose_source(kind)

    def _choose_source(self, kind):
        if kind.downloadable:
            self.alert(
                f"Get {kind.zip_name}",
                f"Download version {bundles.VIEWER_VERSION} from N-able's CDN, or use a zip "
                f"you already have.\n\n{kind.url()}",
                [("cancel", "Cancel"), ("file", "Choose zip\u2026"), ("download", "Download")],
                lambda r: self._download(kind) if r == "download"
                else self._pick_zip(kind) if r == "file" else None,
                default="download")
        else:
            self.alert(
                f"Choose {kind.zip_name}",
                "The Technician Console zip needs your Take Control login to download:\n\n"
                f"{kind.where_to_get}",
                [("cancel", "Cancel"), ("file", "Choose zip\u2026")],
                lambda r: self._pick_zip(kind) if r == "file" else None,
                default="file")

    def _pick_zip(self, kind, runnable=True):
        fd = Gtk.FileDialog(title=f"Choose {kind.zip_name}" if kind else "Choose a Take Control zip")
        f = Gtk.FileFilter()
        f.set_name("Zip archives")
        f.add_pattern("*.zip")
        f.add_pattern("*.ZIP")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        fd.set_filters(store)
        downloads = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD)
        if downloads:
            fd.set_initial_folder(Gio.File.new_for_path(downloads))

        def on_done(dialog, result):
            try:
                gfile = dialog.open_finish(result)
            except GLib.Error:
                return  # cancelled
            if gfile and gfile.get_path():
                self._stage(gfile.get_path(), kind.key if kind else None, runnable)
        fd.open(self, None, on_done)

    def _download(self, kind):
        dest = bundles.staging_root() / "downloads" / bundles.VIEWER_VERSION / kind.zip_name
        self.toast(f"Downloading {kind.zip_name}\u2026")
        self.run_async(lambda: bundles.download(kind.url(), dest),
                       lambda path: self._stage(str(path), kind.key, True), "Download")

    def _stage(self, path, expected, runnable):
        self.run_async(lambda: bundles.stage(path, expected_kind=expected),
                       lambda staged: self.review(staged, runnable), "Reading the zip")

    def review(self, staged, runnable=True):
        wine_ok = deps.by_key("wine").present()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.append(wrap_label(f"SHA-256: {staged.sha256}", "caption"))
        danger = False
        for script in staged.scripts():
            rep = inspect.analyze_file(script)
            fs = inspect.findings(rep, self.distro.family, wine_ok)
            danger |= rep.removes_wine and script == staged.install_script
            box.append(wrap_label(str(script.relative_to(staged.root)), "heading"))
            if not fs:
                box.append(wrap_label("Nothing notable.", "dim-label"))
            for f in fs:
                line = Gtk.Box(spacing=8)
                ic = status_icon(f.level)
                ic.set_valign(Gtk.Align.START)
                line.append(ic)
                line.append(wrap_label(f.message))
                box.append(line)
            exp = Gtk.Expander(label="Show script")
            tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            try:
                tv.get_buffer().set_text(script.read_text(encoding="utf-8", errors="replace"))
            except OSError as e:
                tv.get_buffer().set_text(str(e))
            sc = Gtk.ScrolledWindow(min_content_height=220)
            sc.set_child(tv)
            exp.set_child(sc)
            box.append(exp)
        scroller = Gtk.ScrolledWindow(min_content_height=360, propagate_natural_width=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_child(box)

        script = staged.install_script
        if not runnable or not script:
            self.alert(f"{staged.kind.label}", "Nothing has been run.",
                       [("close", "Close")], extra=scroller)
            return
        self.alert(
            "Review before running",
            f"{staged.kind.label}: here's what N-able's scripts will do on this machine. "
            f"{script.name} runs in your terminal next \u2014 answer its questions there.",
            [("cancel", "Cancel"), ("run", f"Run {script.name}")],
            lambda r: self._run_install(staged) if r == "run" else None,
            extra=scroller, default=None if danger else "run",
            destructive="run" if danger else None)

    def _run_install(self, staged):
        def after(rc):
            if rc != 0:
                self.alert("Installer didn't finish",
                           f"{staged.install_script.name} exited with code {rc}. Nothing was "
                           "recorded. Check the terminal output, fix the cause and try again.",
                           [("close", "Close")])
                self.refresh()
                return
            state.record_install(staged.kind.key, staged)
            if staged.kind.protocol_script and staged.protocol_script:
                self.alert(
                    "Register browser links?",
                    "Runs protocolRegister.sh so Remote Control in N-central/N-sight opens "
                    "this Viewer.",
                    [("later", "Later"), ("run", "Register")],
                    lambda r: self.run_in_terminal(staged.protocol_script, "Register browser links",
                                                   lambda _rc: self.refresh())
                    if r == "run" else self.refresh(),
                    default="run")
            else:
                self.toast(f"{staged.kind.label} installed")
                self.refresh()
        self.run_in_terminal(staged.install_script, f"Install {staged.kind.label}", after)

    def run_in_terminal(self, script, title, on_done):
        term = terminal.find_terminal()
        if not term:
            self.alert("No terminal emulator found",
                       "N-able's scripts are interactive and need a terminal. Run this instead:\n\n"
                       f"bash {script}", [("close", "Close")])
            return
        wrapper, status = terminal.write_wrapper(script, title=title)
        try:
            proc = subprocess.Popen(terminal.terminal_argv(term[1], wrapper),
                                    start_new_session=True,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self.alert("Couldn't open a terminal", str(e), [("close", "Close")])
            return
        self.busy(True)
        self.toast(f"Running in {term[0]} \u2014 switch to it to answer questions")

        def poll():
            rc = terminal.read_status(status)
            if rc is not None:
                self.busy(False)
                on_done(rc)
                return False
            code = proc.poll()
            if code not in (None, 0):
                # Terminal itself failed before the wrapper wrote a status.
                self.busy(False)
                self.alert("Terminal closed early",
                           f"{term[0]} exited with {code} before the script finished.",
                           [("close", "Close")])
                return False
            return True
        GLib.timeout_add(700, poll)

    # ------------------------------------------------------------ uninstall

    def start_uninstall(self, key):
        kind = bundles.KINDS[key]
        rep = self.report
        choices = [(f"Windows uninstaller: {n}", ("entry", p, g)) for p, g, n in rep.all_entries]
        rec = rep.installed.get(key)
        vendor = bundles.find_script(Path(rec["bundle"]), kind.uninstall_script) if rec else None
        if vendor:
            choices.append((f"N-able's {vendor.name}", ("vendor", vendor, None)))
        if not choices:
            self.toast("Nothing to uninstall was found")
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        group = None
        buttons = []
        for label, value in choices:
            cb = Gtk.CheckButton(label=label)
            if group:
                cb.set_group(group)
            else:
                group = cb
                cb.set_active(True)
            buttons.append((cb, value))
            box.append(cb)

        def go(resp):
            if resp != "remove":
                return
            how, target, guid = next(v for cb, v in buttons if cb.get_active())
            if how == "entry":
                self._run_windows_uninstaller(key, target, guid)
            else:
                self._run_vendor_uninstall(key, target)

        self.alert(f"Uninstall {kind.label}?",
                   "The Windows uninstaller removes only Take Control. N-able's script "
                   "may do more \u2014 you'll see what before it runs.",
                   [("cancel", "Cancel"), ("remove", "Continue")], go, extra=box,
                   destructive="remove")

    def _run_windows_uninstaller(self, key, prefix, guid):
        def work():
            env = {**os.environ, "WINEPREFIX": str(prefix)}
            return subprocess.run(wine.uninstall_argv(guid), env=env,
                                  capture_output=True, text=True).returncode

        def done(rc):
            if rc == 0:
                state.forget(key)
                self.toast("Uninstalled")
            else:
                self.toast(f"The uninstaller exited with {rc}")
            self.refresh()
        self.run_async(work, done, "Uninstall")

    def _run_vendor_uninstall(self, key, script):
        rep = inspect.analyze_file(script)
        fs = inspect.findings(rep, self.distro.family, True)
        text = "\n\n".join(f.message for f in fs) or "Nothing notable found in the script."

        def go(resp):
            if resp == "run":
                self.run_in_terminal(script, "Uninstall",
                                     lambda rc: (state.forget(key) if rc == 0 else None,
                                                 self.refresh()))
        self.alert("Run N-able's uninstall script?", text,
                   [("cancel", "Cancel"), ("run", "Remove Wine too" if rep.removes_wine else "Run")],
                   go, destructive="run" if rep.removes_wine else None,
                   default=None if rep.removes_wine else "run")

    # ------------------------------------------------------------ links / tweaks

    def repair_links(self):
        def work():
            rep = doctor.run(distro=self.distro, query_wine=False)
            ids = {h.desktop_id for h in rep.handlers}
            changes, unresolved = [], []
            for scheme, current in rep.schemes.items():
                if current in ids:
                    continue
                cands = [h for h in rep.handlers if scheme in h.schemes]
                if not cands:
                    unresolved.append(scheme)
                    continue
                protocol.set_default(scheme, cands[0].desktop_id)  # user dir sorts first
                changes.append(f"{scheme}:// \u2192 {cands[0].desktop_id}")
            return rep.schemes, changes, unresolved

        def done(result):
            schemes, changes, unresolved = result
            if not schemes:
                self.toast("No Take Control link schemes found \u2014 install a Viewer first")
            elif unresolved:
                self.alert("Some links couldn't be fixed",
                           "No Take Control entry claims: " + ", ".join(unresolved)
                           + ". Reinstall the Viewer and let it register browser links.",
                           [("close", "Close")])
            elif changes:
                self.toast("Fixed: " + "; ".join(changes))
            else:
                self.toast("Browser links already point at Take Control")
            self.refresh()
        self.run_async(work, done, "Repairing browser links")

    def on_decorations(self, sw, _pspec):
        if self._rendering or not self.report or not self.report.prefixes:
            return
        prefix = self.report.prefixes[0]
        on = sw.get_active()
        self.run_async(lambda: wine.set_decorations(prefix, on),
                       lambda _r: self.toast(f"Decorations {'on' if on else 'off'} \u2014 "
                                             "restart Take Control to see it"),
                       "Changing the Wine setting")

    # ------------------------------------------------------------ misc

    def on_inspect(self):
        self._pick_zip(None, runnable=False)

    def check_updates(self, manual=False):
        def work():
            return update.newer_app_release(), update.newer_viewer()

        def done(result):
            app, viewer = result
            if app:
                self.toast(f"{APP_NAME} {app[0]} is available", "View",
                           lambda: self.open_uri(app[1]))
            if viewer:
                self.toast(f"N-able announced Linux Viewer {viewer} \u2014 "
                           f"TuxControl uses {bundles.VIEWER_VERSION}")
            if manual and not app and not viewer:
                self.toast("No updates found")

        if manual:
            self.run_async(work, done, "Update check")
        else:
            # Silent background check: don't lock the window for it.
            def target():
                res = work()
                GLib.idle_add(lambda: (done(res), False)[1])
            threading.Thread(target=target, daemon=True).start()

    def on_about(self):
        about = Adw.AboutDialog(
            application_name=APP_NAME, version=VERSION, developer_name="TridentSpoon",
            license_type=Gtk.License.MIT_X11, website=REPO_URL,
            issue_url=f"{REPO_URL}/issues", application_icon="preferences-desktop-remote-desktop",
            comments="Install N-able Take Control's Linux Console and Viewer on any distro.\n\n"
                     "Not affiliated with or endorsed by N-able.")
        about.present(self)


class App(Adw.Application):
    def __init__(self, check_updates=True):
        super().__init__(application_id=APP_ID)
        self._check_updates = check_updates

    def do_activate(self):
        win = self.props.active_window or Window(self, self._check_updates)
        win.present()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tuxcontrol-gui")
    p.add_argument("--no-update-check", action="store_true",
                   help="don't contact GitHub or N-able at startup")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = p.parse_args(argv)
    if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 5):
        print(f"{APP_NAME} needs libadwaita 1.5 or newer "
              f"(found {Adw.get_major_version()}.{Adw.get_minor_version()}).", file=sys.stderr)
        return 1
    return App(check_updates=not args.no_update_check).run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
