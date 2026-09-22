import unittest
from tuxcontrol.distro import Distro, parse_os_release, detect


class TestParseOsRelease(unittest.TestCase):
    def test_basic(self):
        text = 'ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04"\n'
        d = parse_os_release(text)
        self.assertEqual(d["ID"], "ubuntu")
        self.assertEqual(d["VERSION_ID"], "22.04")
        self.assertEqual(d["PRETTY_NAME"], "Ubuntu 22.04")

    def test_unquoted(self):
        d = parse_os_release("ID=arch\nVERSION_ID=\n")
        self.assertEqual(d["ID"], "arch")
        self.assertEqual(d["VERSION_ID"], "")

    def test_id_like(self):
        d = parse_os_release('ID=linuxmint\nID_LIKE="ubuntu debian"\n')
        self.assertEqual(d["ID_LIKE"], "ubuntu debian")

    def test_comments_and_blank_lines(self):
        d = parse_os_release("# comment\n\nID=fedora\n")
        self.assertEqual(d["ID"], "fedora")
        self.assertNotIn("#", d)

    def test_single_quotes(self):
        d = parse_os_release("NAME='Arch Linux'\n")
        self.assertEqual(d["NAME"], "Arch Linux")

    def test_backslash_escape(self):
        d = parse_os_release('PRETTY_NAME="Foo \\"Bar\\""\n')
        self.assertEqual(d["PRETTY_NAME"], 'Foo "Bar"')


class TestDistroFamily(unittest.TestCase):
    def _d(self, id_, like=""):
        return Distro(id=id_, like=tuple(like.split()) if like else ())

    def test_ubuntu(self):
        self.assertEqual(self._d("ubuntu").family, "debian")

    def test_arch(self):
        self.assertEqual(self._d("arch").family, "arch")

    def test_cachyos(self):
        self.assertEqual(self._d("cachyos").family, "arch")

    def test_fedora(self):
        self.assertEqual(self._d("fedora").family, "fedora")

    def test_opensuse(self):
        self.assertEqual(self._d("opensuse-tumbleweed").family, "suse")

    def test_void(self):
        self.assertEqual(self._d("void").family, "void")

    def test_solus(self):
        self.assertEqual(self._d("solus").family, "solus")

    def test_alpine(self):
        self.assertEqual(self._d("alpine").family, "alpine")

    def test_unknown_falls_through_to_like(self):
        # e.g. MX Linux: ID=mx, ID_LIKE=debian
        self.assertEqual(self._d("mx", "debian").family, "debian")

    def test_totally_unknown(self):
        self.assertEqual(self._d("gentoo").family, "unknown")

    def test_raspbian_via_id_like(self):
        self.assertEqual(self._d("raspbian", "debian").family, "debian")


class TestDistroSupportLevel(unittest.TestCase):
    def test_tested_ubuntu_2004(self):
        d = Distro(id="ubuntu", version_id="20.04")
        self.assertEqual(d.support_level, "tested")

    def test_tested_ubuntu_2204(self):
        d = Distro(id="ubuntu", version_id="22.04")
        self.assertEqual(d.support_level, "tested")

    def test_tested_fedora_36(self):
        d = Distro(id="fedora", version_id="36")
        self.assertEqual(d.support_level, "tested")

    def test_family_ubuntu_2404(self):
        d = Distro(id="ubuntu", version_id="24.04")
        self.assertEqual(d.support_level, "family")

    def test_family_debian(self):
        d = Distro(id="debian", version_id="12")
        self.assertEqual(d.support_level, "family")

    def test_adapted_arch(self):
        d = Distro(id="arch")
        self.assertEqual(d.support_level, "adapted")

    def test_adapted_void(self):
        d = Distro(id="void")
        self.assertEqual(d.support_level, "adapted")


class TestDetect(unittest.TestCase):
    def test_detect_from_text(self, tmp_path=None):
        import tempfile, os
        text = 'ID=ubuntu\nVERSION_ID="22.04"\nPRETTY_NAME="Ubuntu 22.04"\nID_LIKE=debian\n'
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
            f.write(text)
            name = f.name
        try:
            d = detect(name)
            self.assertEqual(d.id, "ubuntu")
            self.assertEqual(d.version_id, "22.04")
            self.assertIn("debian", d.like)
        finally:
            os.unlink(name)

    def test_detect_missing_file_returns_default(self):
        # Patch read_text on pathlib.Path so both candidates look absent.
        from unittest.mock import patch
        with patch("pathlib.Path.read_text", side_effect=OSError):
            d = detect("/nonexistent/os-release")
        self.assertEqual(d.id, "linux")
