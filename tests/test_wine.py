import unittest
from tuxcontrol.wine import (
    parse_uninstaller_list, parse_reg_query, take_control_entries,
    expand_prefix, TAKE_CONTROL_NAMES,
)
from pathlib import Path


class TestParseUninstallerList(unittest.TestCase):
    SAMPLE = (
        "{12345678-1234-1234-1234-123456789ABC}|||Take Control Agent\n"
        "{DEADBEEF-DEAD-DEAD-DEAD-DEADDEADBEAD}|||Wine Mono 8.1.0\n"
        "bad line without separator\n"
        "\n"
    )

    def test_basic(self):
        result = parse_uninstaller_list(self.SAMPLE)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][1], "Take Control Agent")
        self.assertEqual(result[1][1], "Wine Mono 8.1.0")

    def test_empty(self):
        self.assertEqual(parse_uninstaller_list(""), [])

    def test_no_separator_skipped(self):
        result = parse_uninstaller_list("bad line\n")
        self.assertEqual(result, [])


class TestTakeControlEntries(unittest.TestCase):
    def test_finds_take_control(self):
        entries = [
            ("{AAAA}", "Take Control Agent"),
            ("{BBBB}", "Wine Mono"),
            ("{CCCC}", "N-able Remote Control"),
        ]
        found = take_control_entries(entries)
        self.assertEqual(len(found), 2)
        guids = [g for g, _ in found]
        self.assertIn("{AAAA}", guids)
        self.assertIn("{CCCC}", guids)

    def test_case_insensitive(self):
        entries = [("{X}", "TAKE CONTROL Viewer")]
        self.assertEqual(len(take_control_entries(entries)), 1)

    def test_beanywhere(self):
        entries = [("{X}", "BeAnywhere Support Express")]
        self.assertEqual(len(take_control_entries(entries)), 1)

    def test_no_match(self):
        entries = [("{X}", "Notepad++"), ("{Y}", "Wine Gecko 2.47")]
        self.assertEqual(take_control_entries(entries), [])


class TestParseRegQuery(unittest.TestCase):
    SAMPLE = (
        "\nHKEY_CURRENT_USER\\Software\\Wine\\X11 Driver\n"
        "    Decorated    REG_SZ    Y\n"
        "    UseXVidMode  REG_SZ    N\n"
    )

    def test_finds_value(self):
        self.assertEqual(parse_reg_query(self.SAMPLE, "Decorated"), "Y")

    def test_case_insensitive(self):
        self.assertEqual(parse_reg_query(self.SAMPLE, "decorated"), "Y")

    def test_missing_returns_none(self):
        self.assertIsNone(parse_reg_query(self.SAMPLE, "NonExistent"))

    def test_empty_input(self):
        self.assertIsNone(parse_reg_query("", "Decorated"))


class TestExpandPrefix(unittest.TestCase):
    def test_dollar_home(self):
        home = str(Path.home())
        result = expand_prefix("$HOME/.wine-tc")
        self.assertTrue(str(result).startswith(home))

    def test_brace_home(self):
        home = str(Path.home())
        result = expand_prefix("${HOME}/.wine")
        self.assertTrue(str(result).startswith(home))

    def test_tilde(self):
        home = str(Path.home())
        result = expand_prefix("~/.wine")
        self.assertTrue(str(result).startswith(home))
