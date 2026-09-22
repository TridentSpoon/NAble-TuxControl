import unittest
from tuxcontrol.deps import (
    install_command, missing, packages_for, parse_wine_version,
    wine_version_string, parse_multilib, DEPENDENCIES, by_key,
)


class TestInstallCommand(unittest.TestCase):
    def test_arch(self):
        cmd = install_command("arch", ["wine", "gnupg"])
        self.assertEqual(cmd[:2], ["pacman", "-S"])
        self.assertIn("wine", cmd)
        self.assertIn("gnupg", cmd)

    def test_debian_no_wine(self):
        cmd = install_command("debian", ["gpg"])
        self.assertIn("apt-get install", " ".join(cmd))
        self.assertNotIn("dpkg --add-architecture", " ".join(cmd))

    def test_debian_with_wine_adds_i386(self):
        cmd = install_command("debian", ["wine", "gpg"])
        joined = " ".join(cmd)
        self.assertIn("dpkg --add-architecture i386", joined)
        self.assertIn("wine", joined)

    def test_fedora(self):
        cmd = install_command("fedora", ["wine"])
        self.assertEqual(cmd[:2], ["dnf", "install"])

    def test_suse(self):
        cmd = install_command("suse", ["wine"])
        self.assertEqual(cmd[0], "zypper")

    def test_void(self):
        cmd = install_command("void", ["wine"])
        self.assertEqual(cmd[0], "xbps-install")

    def test_solus(self):
        cmd = install_command("solus", ["wine"])
        self.assertEqual(cmd[0], "eopkg")

    def test_alpine(self):
        cmd = install_command("alpine", ["wine"])
        self.assertEqual(cmd[0], "apk")

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            install_command("gentoo", ["wine"])

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            install_command("arch", [])

    def test_deduplication(self):
        cmd = install_command("arch", ["wine", "wine", "gnupg"])
        self.assertEqual(cmd.count("wine"), 1)


class TestMissing(unittest.TestCase):
    def test_all_present(self):
        result = missing(which=lambda _: "/usr/bin/wine")
        self.assertEqual(result, [])

    def test_nothing_present(self):
        result = missing(which=lambda _: None)
        required = [d for d in result if d.required]
        self.assertTrue(len(required) > 0)

    def test_only_required(self):
        result = missing(which=lambda _: None, include_optional=False)
        self.assertTrue(all(d.required for d in result))

    def test_optional_included(self):
        result = missing(which=lambda _: None, include_optional=True)
        self.assertTrue(any(not d.required for d in result))


class TestPackagesFor(unittest.TestCase):
    def test_arch(self):
        pkgs = packages_for(DEPENDENCIES, "arch")
        self.assertIn("wine", pkgs)
        self.assertIn("gnupg", pkgs)

    def test_debian(self):
        pkgs = packages_for(DEPENDENCIES, "debian")
        self.assertIn("wine", pkgs)
        self.assertIn("gpg", pkgs)

    def test_unknown_returns_empty_for_each(self):
        wine_dep = by_key("wine")
        self.assertEqual(wine_dep.packages_for("unknown"), ())


class TestWineVersion(unittest.TestCase):
    def test_parse_staging(self):
        self.assertEqual(parse_wine_version("wine-9.21 (Staging)"), (9, 21, 0))

    def test_parse_plain(self):
        self.assertEqual(parse_wine_version("wine-8.0.2"), (8, 0, 2))

    def test_parse_none(self):
        self.assertIsNone(parse_wine_version("not wine output"))

    def test_parse_empty(self):
        self.assertIsNone(parse_wine_version(""))

    def test_wine_version_string_no_wine(self):
        result = wine_version_string(run=lambda *_, **__: None)
        self.assertIsNone(result)


class TestParseMultilib(unittest.TestCase):
    def test_enabled(self):
        self.assertTrue(parse_multilib("[multilib]\nInclude = /etc/pacman.d/mirrorlist\n"))

    def test_disabled_comment(self):
        self.assertFalse(parse_multilib("#[multilib]\n#Include = ...\n"))

    def test_absent(self):
        self.assertFalse(parse_multilib("[core]\n[extra]\n"))
