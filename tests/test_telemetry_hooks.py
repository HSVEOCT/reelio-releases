"""Verify optional reporting cannot change a successful operation's result."""
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

import test_installer
import test_updater


class ReportingHookTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_installer.InstallerTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_failed_statistics_download_still_completes_fresh_install(self):
        alternate = self.fixture.root / "standalone"
        alternate.mkdir()
        shutil.copyfile(test_installer.ROOT / "install.sh", alternate / "install.sh")
        (self.fixture.bin / "curl").rename(self.fixture.bin / "fixture-curl")
        self.fixture.tool("curl", '''case "$*" in
          *reelio-telemetry.py*) exit 23;;
          *) exec "$(dirname "$0")/fixture-curl" "$@";;
        esac''')
        with patch.object(test_installer, "ROOT", alternate):
            result = self.fixture.run_setup(REELIO_TELEMETRY="1")
        self.assertIn("health checks passed", result.stdout)
        self.assertTrue((self.fixture.target / ".env").is_file())
        self.assertFalse((self.fixture.target / ".reelio-setup-pending").exists())

    def test_statistics_helper_failure_does_not_raise_from_updater(self):
        with patch.object(test_updater.updater.subprocess, "run", side_effect=OSError("fixture only")):
            test_updater.updater.report_statistics(self.fixture.target, "reelio-public", "1.0.18")

    def test_opt_out_survives_unavailable_helper(self):
        alternate = self.fixture.root / "standalone"
        alternate.mkdir()
        shutil.copyfile(test_installer.ROOT / "install.sh", alternate / "install.sh")
        with patch.object(test_installer, "ROOT", alternate):
            self.fixture.run_setup(REELIO_TELEMETRY="0")
        self.assertTrue((self.fixture.target / ".reelio-telemetry.disabled").is_file())


if __name__ == "__main__":
    unittest.main()
