import os
import tempfile
import unittest
from pathlib import Path

from tuxcontrol.protocol import find_handlers, parse_desktop_entry, query_default


TAKE_CONTROL_DESKTOP = """\
[Desktop Entry]
Type=Application
Name=Take Control Viewer
Exec=wine /home/user/.wine/drive_c/TC/viewer.exe %u
MimeType=x-scheme-handler/ncentral;x-scheme-handler/nsight;
"""

OTHER_DESKTOP = """\
[Desktop Entry]
Type=Application
Name=Firefox
Exec=firefox %u
MimeType=x-scheme-handler/https;
"""

BROKEN_DESKTOP = "not ini format at all }{{"


class TestParseDesktopEntry(unittest.TestCase):
    def test_take_control(self):
        name, exec_, schemes = parse_desktop_entry(TAKE_CONTROL_DESKTOP)
        self.assertEqual(name, "Take Control Viewer")
        self.assertIn("ncentral", schemes)
        self.assertIn("nsight", schemes)

    def test_other(self):
        name, exec_, schemes = parse_desktop_entry(OTHER_DESKTOP)
        self.assertEqual(name, "Firefox")
        self.assertNotIn("ncentral", schemes)

    def test_broken_returns_none(self):
        self.assertIsNone(parse_desktop_entry(BROKEN_DESKTOP))

    def test_no_desktop_entry_section(self):
        self.assertIsNone(parse_desktop_entry("[OtherSection]\nKey=value\n"))

    def test_no_schemes(self):
        result = parse_desktop_entry("[Desktop Entry]\nName=X\nExec=y\n")
        self.assertIsNotNone(result)
        _, _, schemes = result
        self.assertEqual(schemes, ())


class TestFindHandlers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        apps_dir = Path(self.tmp) / "applications"
        apps_dir.mkdir()
        (apps_dir / "takecontrol.desktop").write_text(TAKE_CONTROL_DESKTOP)
        (apps_dir / "firefox.desktop").write_text(OTHER_DESKTOP)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finds_take_control(self):
        dirs = [Path(self.tmp) / "applications"]
        handlers = find_handlers(dirs)
        self.assertEqual(len(handlers), 1)
        self.assertIn("ncentral", handlers[0].schemes)

    def test_ignores_non_tc(self):
        dirs = [Path(self.tmp) / "applications"]
        handlers = find_handlers(dirs)
        names = [h.name for h in handlers]
        self.assertNotIn("Firefox", names)

    def test_empty_dir(self):
        handlers = find_handlers([Path(self.tmp) / "nonexistent"])
        self.assertEqual(handlers, [])

    def test_earlier_dir_shadows_later(self):
        apps1 = Path(self.tmp) / "apps1"
        apps2 = Path(self.tmp) / "apps2"
        apps1.mkdir()
        apps2.mkdir()
        (apps1 / "tc.desktop").write_text(TAKE_CONTROL_DESKTOP)
        (apps2 / "tc.desktop").write_text(TAKE_CONTROL_DESKTOP)
        handlers = find_handlers([apps1, apps2])
        # Same desktop_id from both dirs -- should appear only once.
        self.assertEqual(len(handlers), 1)


class TestQueryDefault(unittest.TestCase):
    def test_no_xdg_mime_returns_none(self):
        result = query_default("ncentral", run=lambda *_a, **_k: None)
        self.assertIsNone(result)
