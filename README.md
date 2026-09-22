# NAble TuxControl

*Take Control, on whatever Linux you actually run.*

A helper for Linux IT admins who need N-able Take Control on their own
workstation: the standalone **Technician Console**, or the **Integrated
Viewer** that N-central and N-sight launch when you click Remote Control.
It's a GTK4/libadwaita GUI plus a CLI, sharing the same safety rails.

N-able does ship Linux builds of both. They run under Wine, and they're
installed by shell scripts that N-able tested on Ubuntu 20/22 and Fedora 36.
On anything else, including Arch/CachyOS and openSUSE, those scripts can
trip over the one step they assume: installing Wine with a package manager
your system doesn't have. TuxControl sorts that out first, then gets out
of the way and lets N-able's own installer do the rest.

> Not affiliated with or endorsed by N-able. "N-able", "Take Control",
> "N-central" and "N-sight" are N-able's trademarks. TuxControl doesn't
> include or redistribute any N-able software; it works with the zips you
> download from N-able.

## What it does

1. **Checks the machine.** Distro and how close it is to what N-able tested,
   whether you're on Wayland with XWayland available (Wine needs it), Wine's
   version, and whether Take Control is already installed in a Wine prefix.
   This check is read-only. In particular it never creates a Wine prefix by
   accident, which any stray `wine` command would otherwise do.
2. **Installs dependencies natively.** Wine, GnuPG and xdg-utils (plus
   optional curl and winetricks) with *your* package manager: pacman, apt,
   dnf or zypper. The exact command is shown before it runs, and it's the
   only step that ever runs as root. With Wine already present, N-able's
   script takes its "Wine is already installed" path instead of reaching
   for apt.
3. **Gets the zip.** The two Viewers download straight from N-able's CDN
   (you're shown the URL first). The Technician Console can't be, because
   it sits behind your Take Control login, so you download `LinuxConsole.zip`
   from **Admin Area → Downloads → Technician Console → Linux** and point
   TuxControl at it.
4. **Stages it safely.** Verifies it's a real zip, shows its SHA-256,
   rejects path-traversal and symlink tricks, and extracts it to
   `~/.local/share/nable-tuxcontrol/bundles/`. Scripts are made executable
   for you only. N-able's README says `sudo chmod +x *`, but there's no
   reason for root to own a copy in your home folder.
5. **Tells you what the scripts will do before they run.** Every script in
   the bundle is read and summarised for *this* machine: package managers it
   calls that your system doesn't have, whether it asks for sudo, whether
   it's interactive, which browser link schemes and Wine prefix it uses,
   what it downloads, and which system paths it touches. The full text is
   one click away.
6. **Runs N-able's installer in your terminal.** The scripts ask Y/N
   questions and may call sudo themselves, so they need a real terminal:
   TuxControl opens your desktop's own (Konsole on KDE, Ptyxis/Console/
   GNOME Terminal on GNOME, and so on) and waits for the result. Only a
   successful exit is recorded as installed.
7. **Wires up the browser.** For the Viewers it offers to run
   `protocolRegister.sh` afterwards, then checks that Remote Control links
   actually resolve to Take Control. If something else has grabbed the
   scheme, **Repair browser links** points it back.

## Requirements

- Python 3.8+
- For the GUI: **GTK 4.10+** and **libadwaita 1.5+** with PyGObject
  (anything with GNOME 46 or newer: Ubuntu 24.04, Fedora 40, current Arch).
  - Arch/CachyOS: `sudo pacman -S python-gobject gtk4 libadwaita`
  - Debian/Ubuntu: `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1`
  - Fedora: `sudo dnf install python3-gobject gtk4 libadwaita`
- `pkexec` (polkit) for the GUI's one root step; `sudo` for the CLI's.
- A terminal emulator, for N-able's interactive scripts.

The CLI has no dependencies beyond Python, which makes it the right tool
over SSH (for everything except the steps that open Wine windows, which
need your desktop session).

## Installing

```
git clone https://github.com/TridentSpoon/NAble-TuxControl.git
cd NAble-TuxControl
./install.sh
```

That checks the GTK/libadwaita versions, copies the app to
`~/.local/share/nable-tuxcontrol-app`, adds `tuxcontrol` (CLI) and
`tuxcontrol-gui` to `~/.local/bin`, and puts **NAble TuxControl** in your
app menu. To upgrade, `git pull` in your clone and run `./install.sh` again.
Your staged bundles and install records live separately in
`~/.local/share/nable-tuxcontrol` and survive reinstalls.

Or run it straight from the clone: `python3 tuxcontrol_gui.py` /
`python3 tuxcontrol_cli.py`.

## Usage

### GUI

The window reads top to bottom in the order you'd work: **This machine**,
**Dependencies** (with *Install missing…*), **Take Control** (Install /
Reinstall / Uninstall for each of the three components), **Browser links**,
and **Wine tweaks**. The ↻ button re-runs the machine check; the menu has
*Inspect a zip…* (the full review without running anything), *Repair
browser links*, *Check for updates* and *About*.

`--no-update-check` stops it contacting GitHub and N-able at startup.

### CLI

```
tuxcontrol                      # menu
tuxcontrol doctor               # read-only machine check (exit 1 if something's failing)
tuxcontrol deps [--optional]    # install missing dependencies via sudo
tuxcontrol inspect ZIP          # stage + review a zip; runs nothing
tuxcontrol install nsight       # download, review, run installNSight.sh, register links
tuxcontrol install ncentral --viewer-version 7.44.08
tuxcontrol install console --zip ~/Downloads/LinuxConsole.zip
tuxcontrol register nsight      # re-run protocolRegister.sh
tuxcontrol repair-links
tuxcontrol decorations on|off|status
tuxcontrol uninstall console
tuxcontrol updates
```

### Uninstalling Take Control

You get a choice, and the difference matters. N-able's docs say
`uninstallConsole.sh` removes **Wine itself**, which takes out every other
Windows app you run under Wine. So TuxControl offers the Windows
uninstaller for each Take Control entry it finds in your Wine prefixes
first. That removes only Take Control. N-able's script is still available,
but if TuxControl's reading of it spots Wine being removed, it says so and
makes you confirm (in the CLI, by typing `remove wine`).

TuxControl itself never removes Wine. If you want it gone, use your package
manager.

### Window decorations

N-able's known issue: under some window managers, Wine's title bars or
minimise/maximise/close buttons misbehave. The fix is winecfg's *Allow the
window manager to decorate the windows* setting, but their Console and
Viewer notes give opposite advice about which way to set it. The **Wine
tweaks** switch (or `tuxcontrol decorations on|off`) flips it directly in
the prefix; try whichever state you're not in and restart Take Control.

### Viewer versions

The download defaults to Linux Viewer **7.44.08** (April 2026). N-able has
kept the CDN path's shape stable between releases, so `--viewer-version`
works for newer ones, and *Check for updates* reads N-able's Take Control
release feed and tells you when a newer Linux Viewer has been announced.

## Project layout

```
tuxcontrol/
  distro.py      os-release parsing, package-manager family, support level
  deps.py        dependency checks and per-distro install commands
  bundles.py     the three N-able bundles, safe staging, CDN download
  inspect.py     reads vendor scripts and reports what they'll do here
  wine.py        prefix queries (never creates one), uninstallers, decorations
  protocol.py    browser link-handler detection and repair (xdg-mime)
  terminal.py    runs interactive scripts in the user's terminal emulator
  privileged.py  the only root path: pkexec (GUI) / sudo (CLI) package installs
  doctor.py      whole-machine check shared by both front ends
  state.py       record of what was installed, for status and uninstall
  update.py      quiet update checks (GitHub release, N-able feed)
  cli.py         CLI: subcommands + menu
  gui.py         GTK4/libadwaita front end
tuxcontrol_cli.py   CLI entry point
tuxcontrol_gui.py   GUI entry point
```

## Running tests

```
python3 -m unittest discover -s tests -v
```

Covers distro detection, dependency commands, script analysis, safe
extraction (zip-slip and symlinks), Wine output parsing, link-handler
discovery, the terminal wrapper and update-feed parsing. No Wine, network
or root needed: N-able's bundles are faked with small zips.

## Known limits

- The script reader is heuristic, not a shell parser. It's there to flag
  things worth a look; the full script is always shown alongside.
- TuxControl can't see inside N-able's scripts before you get the zip, so
  if a future release changes script names, `bundles.py` is the one place
  to update.
- The standalone Console zip needs your N-able login, so it can't be
  downloaded automatically.

## License

MIT — see [LICENSE](LICENSE).
