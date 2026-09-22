"""The three things N-able ships for Linux technicians, and how to stage them.

* Technician Console (standalone Take Control) -- ``LinuxConsole.zip``, only
  downloadable from the Take Control Admin Area (it needs your login), so the
  user always supplies this one.
* Integrated Viewer for N-central -- ``LinuxNCentral.zip`` on N-able's CDN.
* Integrated Viewer for N-sight   -- ``LinuxNSight.zip`` on N-able's CDN.

"Staging" = verifying the zip, extracting it safely into our own data folder
and marking its scripts executable for *this user only* (N-able's README says
``sudo chmod +x *``; there's no reason for root to own a copy in your home).
"""

import hashlib
import os
import stat
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import data_dir

# Latest Integrated Linux Viewer N-able has announced. The CDN path has kept
# the same shape across releases, so a newer version just changes this string
# (or pass --viewer-version on the command line).
VIEWER_VERSION = "7.44.08"

_VIEWER_URLS = {
    "ncentral": "https://swi-rc.cdn-sw.net/n-central/Linux_viewer/{v}/LinuxNCentral.zip",
    "nsight": "https://swi-rc.cdn-sw.net/logicnow/linux_viewer/{v}/LinuxNSight.zip",
}


@dataclass(frozen=True)
class BundleKind:
    key: str
    label: str
    zip_name: str
    install_script: str
    uninstall_script: str
    protocol_script: str = ""   # viewers only
    where_to_get: str = ""

    @property
    def downloadable(self) -> bool:
        return self.key in _VIEWER_URLS

    def url(self, version: str = VIEWER_VERSION) -> str:
        return _VIEWER_URLS[self.key].format(v=version)


KINDS = {
    "console": BundleKind(
        "console", "Technician Console (standalone)", "LinuxConsole.zip",
        "installConsole.sh", "uninstallConsole.sh",
        where_to_get="Take Control Admin Area \u2192 Downloads \u2192 Technician Console \u2192 Linux",
    ),
    "ncentral": BundleKind(
        "ncentral", "Integrated Viewer \u2014 N-central", "LinuxNCentral.zip",
        "installNcentral.sh", "UninstallNCentral.sh", "protocolRegister.sh",
        where_to_get="N-able CDN (TuxControl can download it)",
    ),
    "nsight": BundleKind(
        "nsight", "Integrated Viewer \u2014 N-sight", "LinuxNSight.zip",
        "installNSight.sh", "UninstallNSight.sh", "protocolRegister.sh",
        where_to_get="N-able CDN (TuxControl can download it)",
    ),
}


class BundleError(Exception):
    pass


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def check_member_name(name: str) -> PurePosixPath:
    """Reject anything that could land outside the destination (zip-slip)."""
    p = PurePosixPath(name.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
        raise BundleError(f"refusing unsafe path in zip: {name!r}")
    return p


def identify(names) -> str:
    """Return the BundleKind key whose install script is in ``names``.

    Matching is by basename, case-insensitively -- N-able's own naming isn't
    consistent (installNcentral.sh vs UninstallNCentral.sh).
    """
    basenames = {PurePosixPath(n.replace("\\", "/")).name.lower() for n in names}
    found = [k for k, kind in KINDS.items() if kind.install_script.lower() in basenames]
    if not found:
        raise BundleError(
            "this zip doesn't contain any of N-able's Linux install scripts "
            "(installConsole.sh, installNcentral.sh, installNSight.sh)")
    if len(found) > 1:
        raise BundleError("this zip contains more than one installer; extract it manually")
    return found[0]


def find_script(root: Path, script_name: str):
    """Locate a script anywhere under ``root`` by case-insensitive basename."""
    if not script_name:
        return None
    want = script_name.lower()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower() == want:
                return Path(dirpath) / f
    return None


@dataclass
class StagedBundle:
    kind: BundleKind
    root: Path
    sha256: str
    source: str

    @property
    def install_script(self):
        return find_script(self.root, self.kind.install_script)

    @property
    def uninstall_script(self):
        return find_script(self.root, self.kind.uninstall_script)

    @property
    def protocol_script(self):
        return find_script(self.root, self.kind.protocol_script)

    def scripts(self) -> list:
        return sorted(p for p in self.root.rglob("*.sh") if p.is_file())


def staging_root() -> Path:
    return data_dir() / "bundles"


def stage(zip_path, dest_base: Path = None, expected_kind: str = None) -> StagedBundle:
    """Verify and extract ``zip_path``; return the staged bundle."""
    zip_path = Path(zip_path)
    if not zipfile.is_zipfile(zip_path):
        raise BundleError(f"{zip_path.name} isn't a zip archive")
    digest = sha256(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        for info in infos:
            check_member_name(info.filename)
            if _is_symlink(info):
                raise BundleError(f"refusing symlink in zip: {info.filename!r}")
        kind_key = identify(i.filename for i in infos)
        if expected_kind and kind_key != expected_kind:
            raise BundleError(
                f"expected {KINDS[expected_kind].zip_name}, but this is {KINDS[kind_key].zip_name}")
        base = dest_base if dest_base is not None else staging_root()
        root = base / kind_key / digest[:12]
        root.mkdir(parents=True, exist_ok=True)
        for info in infos:
            rel = check_member_name(info.filename)
            target = root.joinpath(*rel.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    dst.write(buf)
    for script in root.rglob("*.sh"):
        mode = script.stat().st_mode
        script.chmod((mode | stat.S_IRUSR | stat.S_IXUSR) & ~(stat.S_IWGRP | stat.S_IWOTH))
    return StagedBundle(KINDS[kind_key], root, digest, str(zip_path))


def download(url: str, dest: Path, progress=None, timeout=60) -> Path:
    """Download ``url`` to ``dest`` (atomically). ``progress(done, total)``."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "NAble-TuxControl"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            buf = resp.read(1 << 16)
            if not buf:
                break
            out.write(buf)
            done += len(buf)
            if progress:
                progress(done, total)
    if not zipfile.is_zipfile(tmp):
        tmp.unlink(missing_ok=True)
        raise BundleError("the download isn't a zip -- the URL may have moved")
    os.replace(tmp, dest)
    return dest
