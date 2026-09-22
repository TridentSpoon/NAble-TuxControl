import unittest
from tuxcontrol.inspect import (
    analyze_text, findings, strip_comments, PACKAGE_MANAGERS,
)


class TestStripComments(unittest.TestCase):
    def test_removes_full_line(self):
        out = strip_comments("# full comment\necho hi\n")
        self.assertNotIn("full comment", out)
        self.assertIn("echo hi", out)

    def test_keeps_inline_hash(self):
        out = strip_comments("echo ${#var}\n")
        self.assertIn("${#var}", out)

    def test_removes_shebang(self):
        out = strip_comments("#!/bin/bash\necho hi\n")
        self.assertNotIn("#!/bin/bash", out)


class TestAnalyzeText(unittest.TestCase):
    def _r(self, text):
        return analyze_text(text, "<test>")

    def test_detects_apt(self):
        r = self._r("apt-get install -y wine\n")
        self.assertIn("apt", r.package_managers)

    def test_detects_dnf(self):
        r = self._r("dnf install wine\n")
        self.assertIn("dnf", r.package_managers)

    def test_detects_pacman(self):
        r = self._r("pacman -S wine\n")
        self.assertIn("pacman", r.package_managers)

    def test_detects_zypper(self):
        r = self._r("zypper install wine\n")
        self.assertIn("zypper", r.package_managers)

    def test_does_not_detect_pm_in_comment(self):
        r = self._r("# apt-get install wine\n")
        self.assertNotIn("apt", r.package_managers)

    def test_detects_sudo(self):
        r = self._r("sudo rm -rf /tmp\n")
        self.assertTrue(r.uses_root)

    def test_detects_pkexec(self):
        r = self._r("pkexec do-thing\n")
        self.assertTrue(r.uses_root)

    def test_detects_interactive(self):
        r = self._r("read -p 'Continue?' ans\n")
        self.assertTrue(r.interactive)

    def test_detects_scheme(self):
        r = self._r("xdg-mime default foo.desktop x-scheme-handler/ncentral\n")
        self.assertIn("ncentral", r.schemes)

    def test_detects_url(self):
        r = self._r("curl https://example.com/file.exe\n")
        self.assertIn("https://example.com/file.exe", r.downloads)

    def test_detects_wineprefix(self):
        r = self._r('WINEPREFIX="$HOME/.wine-tc" wine start\n')
        self.assertTrue(any("wine-tc" in p for p in r.prefixes))

    def test_detects_wine_removal(self):
        r = self._r("apt-get remove wine\n")
        self.assertTrue(r.removes_wine)

    def test_no_removal_on_install(self):
        r = self._r("apt-get install wine\n")
        self.assertFalse(r.removes_wine)


class TestFindings(unittest.TestCase):
    def _findings(self, text, family="arch", wine_present=True):
        r = analyze_text(text)
        return findings(r, family, wine_present)

    def test_foreign_pm_wine_present(self):
        fs = self._findings("apt-get install wine\n", family="arch", wine_present=True)
        levels = [f.level for f in fs]
        self.assertIn("info", levels)

    def test_foreign_pm_wine_absent(self):
        fs = self._findings("apt-get install wine\n", family="arch", wine_present=False)
        levels = [f.level for f in fs]
        self.assertIn("warn", levels)

    def test_native_pm_no_finding(self):
        fs = self._findings("apt-get install wine\n", family="debian", wine_present=True)
        foreign = [f for f in fs if "apt" in f.message and "doesn't use" in f.message]
        self.assertEqual(foreign, [])

    def test_removes_wine_danger(self):
        fs = self._findings("apt-get remove wine\n", family="debian", wine_present=True)
        levels = [f.level for f in fs]
        self.assertIn("danger", levels)

    def test_sudo_info(self):
        fs = self._findings("sudo do-thing\n")
        self.assertTrue(any("root" in f.message.lower() or "sudo" in f.message.lower() for f in fs))

    def test_scheme_reported(self):
        fs = self._findings("xdg-mime default tc.desktop x-scheme-handler/ncentral\n")
        self.assertTrue(any("ncentral" in f.message for f in fs))
