"""The only code that runs anything as root: installing distro packages.

TuxControl itself never runs as root and never runs N-able's scripts as root
(they call sudo themselves where they need it). The one privileged step is
the package install, and the exact argv is always shown before it runs.
"""

import shlex
import shutil
import subprocess


class PrivilegeError(Exception):
    pass


def describe(argv) -> str:
    return " ".join(shlex.quote(a) for a in argv)


def run_pkexec(argv, timeout=1800):
    """GUI path: graphical polkit prompt. Returns CompletedProcess."""
    if not shutil.which("pkexec"):
        raise PrivilegeError("pkexec isn't installed (it comes with polkit)")
    res = subprocess.run(["pkexec", *argv], capture_output=True, text=True, timeout=timeout)
    # 126: user dismissed the auth dialog; 127: not authorized
    if res.returncode in (126, 127):
        raise PrivilegeError("authentication was cancelled or refused")
    return res


def run_sudo(argv):
    """CLI path: sudo in the current terminal, output streamed live."""
    if not shutil.which("sudo"):
        raise PrivilegeError("sudo isn't installed")
    return subprocess.run(["sudo", *argv])
