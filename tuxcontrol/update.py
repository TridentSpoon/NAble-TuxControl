"""Two quiet update checks. Both return None on any failure: being offline
or rate-limited is not worth an error message.

* App: latest GitHub release of NAble-TuxControl.
* Viewer: newest "Linux Viewer x.y.z" announced on N-able's Take Control
  release-notes feed, so you know when VIEWER_VERSION is behind.
"""

import json
import re
import urllib.request

from . import REPO, VERSION
from .bundles import VIEWER_VERSION

FEED_URL = "https://status.n-able.com/category/nable-take-control/feed/"
_VIEWER_RX = re.compile(r"Linux Viewer\s+(\d+\.\d+\.\d+)", re.IGNORECASE)


def _ver(s: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", s)[:4])


def _get(url: str, timeout=8) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "NAble-TuxControl"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def newer_app_release():
    """(tag, html_url) if a newer release exists, else None."""
    try:
        data = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
        tag = data.get("tag_name", "")
        if tag and _ver(tag) > _ver(VERSION):
            return tag, data.get("html_url", "")
    except Exception:  # noqa: BLE001 -- deliberately silent
        return None
    return None


def latest_viewer_in_feed(xml_text: str):
    versions = _VIEWER_RX.findall(xml_text or "")
    return max(versions, key=_ver) if versions else None


def newer_viewer():
    """Newest announced Linux Viewer version if newer than ours, else None."""
    try:
        latest = latest_viewer_in_feed(_get(FEED_URL).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if latest and _ver(latest) > _ver(VIEWER_VERSION):
        return latest
    return None
