"""Constrained broker checks, without access to real containers."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    import types
    sys.modules.setdefault("fcntl", types.SimpleNamespace())
    # Unix listener isn't used by these portable policy tests.
    import socketserver
    socketserver.UnixStreamServer = socketserver.TCPServer
spec = importlib.util.spec_from_file_location("broker", Path(__file__).resolve().parents[1] / "distribution/reelio-updater.py")
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


class Helper:
    version_tuple = staticmethod(lambda version: tuple(map(int, version.split("."))))
    stable_release = staticmethod(lambda _work: {"version": "1.0.21", "sha256": "a" * 64})
    release_bundle = staticmethod(lambda _manifest, work: work)


temporary_root=Path(__file__).resolve().parents[1]/'.test-temp'
temporary_root.mkdir(exist_ok=True)
tempfile.tempdir=str(temporary_root)


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "VERSION").write_text("1.0.20")
        self.service = broker.Broker(self.root, self.root / "state.json", Helper)

    def test_only_newer_official_stable_release_is_available(self):
        self.assertTrue(self.service.check()["available"])
        (self.root / "VERSION").write_text("1.0.22")
        self.assertFalse(self.service.check()["available"])

    def test_arbitrary_paths_versions_and_checksums_are_refused(self):
        for version, checksum in (("../../evil", "a"*64), ("1.0.21", "http://evil"), ("1.0.21; sh evil", "a"*64)):
            with self.assertRaises(ValueError):
                self.service.start(version, checksum)

    def test_duplicate_update_is_refused(self):
        self.service.lock.acquire()
        with self.assertRaises(ValueError):
            self.service.start("1.0.21", "a" * 64)
        self.service.lock.release()

    def test_changed_release_never_executes_a_command(self):
        self.service.lock.acquire()
        with patch.object(broker.subprocess, "run") as run:
            self.service.update("1.0.21", "b"*64)
            run.assert_not_called()
        self.assertEqual(self.service.result["phase"], "failed")

    def test_failed_helper_is_not_reported_as_success(self):
        self.service.lock.acquire()
        with patch.object(broker.subprocess, "run", return_value=type("Result", (), {"returncode": 1})()) as run:
            self.service.update("1.0.21", "a"*64)
        self.assertEqual(self.service.result["phase"], "failed")
        args = run.call_args
        self.assertIn("--bundle", args.args[0])
        self.assertNotIn("shell", args.kwargs)
        self.assertEqual(args.kwargs["env"]["REELIO_UPDATE_CONFIRM"], "1")

    def test_success_requires_verified_version_and_survives_restart(self):
        def complete(*_args, **_kwargs):
            (self.root / "VERSION").write_text("1.0.21")
            return type("Result", (), {"returncode": 0})()
        self.service.lock.acquire()
        with patch.object(broker.subprocess, "run", side_effect=complete):
            self.service.update("1.0.21", "a"*64)
        restarted = broker.Broker(self.root, self.root / "state.json", Helper)
        self.assertEqual(restarted.status()["phase"], "complete")

    def test_interrupted_update_requires_owner_attention(self):
        self.service.save(phase="updating")
        restarted = broker.Broker(self.root, self.root / "state.json", Helper)
        self.assertEqual(restarted.status()["phase"], "attention")
        with self.assertRaises(ValueError):
            restarted.start("1.0.21", "a"*64)


class StorageTests(unittest.TestCase):
    def test_only_the_registered_runtime_socket_is_excluded_from_data_backup(self):
        helper=broker.load_helper()
        installation=helper.Installation.__new__(helper.Installation)
        installation.pg_mounts=[{"Type":"volume","Name":"pg-data"}]
        socket={"Type":"bind","Source":"/var/lib/reelio-updater-sockets/123456abcdef","Destination":"/run/reelio-updater","RW":False}
        installation.rows={"postgres":{"Id":"pg"},"api":{"Id":"api","Mounts":[socket,{"Type":"volume","Name":"backups"},{"Type":"bind","Source":"/srv/media-settings","Destination":"/settings","RW":False}]}}
        installation.config={"volumes":{}}
        installation.project="fixture"
        with patch.object(helper,"run",return_value=""):
            selected=installation.backup_storage()
        self.assertIn(("volume","backups"),selected)
        self.assertIn(("bind","/srv/media-settings"),selected)
        self.assertNotIn(("bind",socket["Source"]),selected)
        socket["Source"]="/srv/unexpected-data"
        with patch.object(helper,"run",return_value=""),self.assertRaises(helper.UpdateError):
            installation.backup_storage()

    def test_installer_pins_the_exact_distribution_helper(self):
        import hashlib,re
        root=Path(__file__).resolve().parents[1]/"distribution"
        pin=re.search(r"helper_sha=([a-f0-9]{64})",(root/"install.sh").read_text())[1]
        self.assertEqual(pin,hashlib.sha256((root/"guided-update.py").read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
