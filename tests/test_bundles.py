import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from tuxcontrol.bundles import (
    BundleError, check_member_name, identify, sha256, stage,
)


def _make_zip(dest: Path, members: dict, symlinks: list = ()):
    """members: {name: text_content}; symlinks: [(name, target)]"""
    with zipfile.ZipFile(dest, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)
        for name, target in symlinks:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, target)


def _console_zip(dest: Path):
    _make_zip(dest, {
        "installConsole.sh": "#!/bin/bash\necho hello\n",
        "uninstallConsole.sh": "#!/bin/bash\necho bye\n",
    })


def _ncentral_zip(dest: Path):
    _make_zip(dest, {
        "installNcentral.sh": "#!/bin/bash\necho hello\n",
        "UninstallNCentral.sh": "#!/bin/bash\necho bye\n",
        "protocolRegister.sh": "#!/bin/bash\necho register\n",
    })


class TestCheckMemberName(unittest.TestCase):
    def test_ok(self):
        check_member_name("subdir/file.sh")  # should not raise

    def test_absolute_raises(self):
        with self.assertRaises(BundleError):
            check_member_name("/etc/passwd")

    def test_dotdot_raises(self):
        with self.assertRaises(BundleError):
            check_member_name("../../../etc/passwd")

    def test_windows_drive_raises(self):
        with self.assertRaises(BundleError):
            check_member_name("C:\\Windows\\System32\\cmd.exe")


class TestIdentify(unittest.TestCase):
    def test_console(self):
        self.assertEqual(identify(["installConsole.sh", "other.sh"]), "console")

    def test_ncentral(self):
        self.assertEqual(identify(["installNcentral.sh"]), "ncentral")

    def test_nsight(self):
        self.assertEqual(identify(["installNSight.sh"]), "nsight")

    def test_case_insensitive(self):
        self.assertEqual(identify(["InstallConsole.SH"]), "console")

    def test_missing_raises(self):
        with self.assertRaises(BundleError):
            identify(["random.sh", "another.sh"])

    def test_multiple_raises(self):
        with self.assertRaises(BundleError):
            identify(["installConsole.sh", "installNcentral.sh"])


class TestStage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.zip_path = Path(self.tmp) / "LinuxConsole.zip"
        self.dest = Path(self.tmp) / "staged"
        _console_zip(self.zip_path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stage_returns_bundle(self):
        b = stage(self.zip_path, dest_base=self.dest)
        self.assertEqual(b.kind.key, "console")
        self.assertTrue(b.root.is_dir())

    def test_sha256_stored(self):
        b = stage(self.zip_path, dest_base=self.dest)
        self.assertEqual(len(b.sha256), 64)
        self.assertEqual(b.sha256, sha256(self.zip_path))

    def test_scripts_executable(self):
        b = stage(self.zip_path, dest_base=self.dest)
        for s in b.scripts():
            self.assertTrue(s.stat().st_mode & stat.S_IXUSR)

    def test_scripts_not_world_writable(self):
        b = stage(self.zip_path, dest_base=self.dest)
        for s in b.scripts():
            self.assertFalse(s.stat().st_mode & stat.S_IWOTH)

    def test_expected_kind_mismatch_raises(self):
        with self.assertRaises(BundleError):
            stage(self.zip_path, dest_base=self.dest, expected_kind="ncentral")

    def test_not_a_zip_raises(self):
        bad = Path(self.tmp) / "bad.zip"
        bad.write_bytes(b"not a zip")
        with self.assertRaises(BundleError):
            stage(bad, dest_base=self.dest)

    def test_zipslip_raises(self):
        evil = Path(self.tmp) / "evil.zip"
        _make_zip(evil, {
            "installConsole.sh": "#!/bin/bash\n",
            "../../../tmp/evil.txt": "pwned",
        })
        with self.assertRaises(BundleError):
            stage(evil, dest_base=self.dest)

    def test_symlink_raises(self):
        evil = Path(self.tmp) / "symlink.zip"
        _make_zip(evil, {"installConsole.sh": "#!/bin/bash\n"},
                  symlinks=[("link", "/etc/passwd")])
        with self.assertRaises(BundleError):
            stage(evil, dest_base=self.dest)

    def test_install_script_property(self):
        b = stage(self.zip_path, dest_base=self.dest)
        self.assertIsNotNone(b.install_script)
        self.assertTrue(b.install_script.name.lower() == "installconsole.sh")

    def test_ncentral_protocol_script(self):
        nz = Path(self.tmp) / "LinuxNCentral.zip"
        _ncentral_zip(nz)
        b = stage(nz, dest_base=self.dest)
        self.assertIsNotNone(b.protocol_script)
