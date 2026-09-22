import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tuxcontrol.terminal import find_terminal, write_wrapper, read_status, _TERMINALS


class TestFindTerminal(unittest.TestCase):
    def test_finds_present(self):
        name, argv = find_terminal(which=lambda n: "/usr/bin/xterm" if n == "xterm" else None)
        self.assertEqual(name, "xterm")
        self.assertIn("xterm", argv)

    def test_returns_none_when_nothing_present(self):
        result = find_terminal(which=lambda _: None)
        self.assertIsNone(result)

    def test_prefers_first_match(self):
        # If both konsole and xterm are present, konsole should win when on KDE.
        def which(n):
            return f"/usr/bin/{n}" if n in ("konsole", "xterm") else None
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            name, _ = find_terminal(which=which)
        self.assertEqual(name, "konsole")

    def test_gnome_prefers_ptyxis(self):
        def which(n):
            return f"/usr/bin/{n}" if n in ("ptyxis", "gnome-terminal") else None
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}):
            name, _ = find_terminal(which=which)
        self.assertEqual(name, "ptyxis")

    def test_mate_prefers_mate_terminal(self):
        def which(n):
            return "/usr/bin/mate-terminal" if n == "mate-terminal" else None
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "MATE"}):
            name, _ = find_terminal(which=which)
        self.assertEqual(name, "mate-terminal")

    def test_lxqt_prefers_lxterminal(self):
        def which(n):
            return "/usr/bin/lxterminal" if n == "lxterminal" else None
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "LXQt"}):
            name, _ = find_terminal(which=which)
        self.assertEqual(name, "lxterminal")

    def test_terminals_table_includes_new_entries(self):
        names = [t for t, _ in _TERMINALS]
        self.assertIn("lxterminal", names)
        self.assertIn("mate-terminal", names)
        self.assertIn("terminator", names)
        self.assertIn("urxvt", names)


class TestWriteWrapper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.script = Path(self.tmp) / "test.sh"
        self.script.write_text("#!/bin/bash\necho done\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_creates_wrapper_and_status(self):
        wrapper, status = write_wrapper(self.script)
        self.assertTrue(wrapper.exists())
        self.assertFalse(status.exists())

    def test_wrapper_is_executable(self):
        wrapper, _ = write_wrapper(self.script)
        import stat
        self.assertTrue(wrapper.stat().st_mode & stat.S_IXUSR)

    def test_wrapper_contains_script_path(self):
        wrapper, _ = write_wrapper(self.script)
        text = wrapper.read_text()
        self.assertIn(str(self.script), text)

    def test_custom_title(self):
        wrapper, _ = write_wrapper(self.script, title="My Test")
        self.assertIn("My Test", wrapper.read_text())


class TestReadStatus(unittest.TestCase):
    def test_reads_exit_code(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".status") as f:
            f.write("0\n")
            name = f.name
        try:
            self.assertEqual(read_status(Path(name)), 0)
        finally:
            os.unlink(name)

    def test_reads_nonzero(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".status") as f:
            f.write("127\n")
            name = f.name
        try:
            self.assertEqual(read_status(Path(name)), 127)
        finally:
            os.unlink(name)

    def test_missing_file_returns_none(self):
        self.assertIsNone(read_status(Path("/nonexistent/status")))

    def test_non_integer_returns_none(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".status") as f:
            f.write("not a number\n")
            name = f.name
        try:
            self.assertIsNone(read_status(Path(name)))
        finally:
            os.unlink(name)
