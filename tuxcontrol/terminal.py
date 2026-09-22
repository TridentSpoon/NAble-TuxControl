"""Run N-able's interactive scripts where the admin can answer them.

The vendor installers ask Y/N questions and may call sudo, so they need a real
terminal. The CLI just runs them in its own. The GUI opens the user's terminal
emulator on a small wrapper that writes the script's exit code to a status
file; the GUI polls that file, which works the same whether or not the
terminal forks into the background.
"""

import os
import shlex
import shutil
import tempfile
from pathlib import Path

# (binary, argv prefix placed before "bash <wrapper>")
_TERMINALS = (
    ("konsole", ["konsole", "-e"]),
    ("gnome-terminal", ["gnome-terminal", "--"]),
    ("kgx", ["kgx", "--"]),
    ("ptyxis", ["ptyxis", "--new-window", "--"]),
    ("xfce4-terminal", ["xfce4-terminal", "-x"]),
    ("mate-terminal", ["mate-terminal", "-x"]),
    ("lxterminal", ["lxterminal", "-e"]),
    ("tilix", ["tilix", "-e"]),
    ("terminator", ["terminator", "-x"]),
    ("alacritty", ["alacritty", "-e"]),
    ("kitty", ["kitty"]),
    ("foot", ["foot"]),
    ("wezterm", ["wezterm", "start", "--"]),
    ("urxvt", ["urxvt", "-e"]),
    ("rxvt", ["rxvt", "-e"]),
    ("xterm", ["xterm", "-e"]),
    ("x-terminal-emulator", ["x-terminal-emulator", "-e"]),
)


def _desktop_preference() -> tuple:
    """Put the desktop's own terminal first (Konsole on KDE, etc.)."""
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    if "kde" in desktop:
        return ("konsole",)
    if "gnome" in desktop:
        return ("ptyxis", "kgx", "gnome-terminal")
    if "xfce" in desktop:
        return ("xfce4-terminal",)
    if "mate" in desktop:
        return ("mate-terminal",)
    if "lxqt" in desktop or "lxde" in desktop:
        return ("lxterminal",)
    return ()


def find_terminal(which=shutil.which):
    order = list(_desktop_preference()) + [t for t, _ in _TERMINALS]
    table = dict(_TERMINALS)
    for name in dict.fromkeys(order):
        if which(name):
            return name, list(table[name])
    return None


WRAPPER = """#!/usr/bin/env bash
cd {cwd} || {{ echo 126 > {status}.tmp; mv -f {status}.tmp {status}; exit 126; }}
printf '\\n  NAble TuxControl is running: %s\\n  (answer any questions below)\\n\\n' {title}
bash {script} {args}
rc=$?
echo "$rc" > {status}.tmp && mv -f {status}.tmp {status}
printf '\\n  Finished with exit code %s. Press Enter to close this window.\\n' "$rc"
read -r _
"""


def write_wrapper(script: Path, args=(), title: str = "", workdir: Path = None):
    """Create the wrapper; return (wrapper_path, status_path)."""
    script = Path(script)
    tmpdir = Path(tempfile.mkdtemp(prefix="tuxcontrol-"))
    status = tmpdir / "exit-status"
    wrapper = tmpdir / "run.sh"
    wrapper.write_text(WRAPPER.format(
        cwd=shlex.quote(str(workdir or script.parent)),
        status=shlex.quote(str(status)),
        title=shlex.quote(title or script.name),
        script=shlex.quote(str(script)),
        args=" ".join(shlex.quote(a) for a in args),
    ), encoding="utf-8")
    wrapper.chmod(0o700)
    return wrapper, status


def terminal_argv(terminal_prefix: list, wrapper: Path) -> list:
    return [*terminal_prefix, "bash", str(wrapper)]


def read_status(status: Path):
    """Exit code once the script has finished, else None."""
    try:
        return int(Path(status).read_text().strip())
    except (OSError, ValueError):
        return None
