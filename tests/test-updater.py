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


class BootstrapComposeTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("bootstrap", Path(__file__).resolve().parents[1] / "distribution/enable-web-updates.py")
        self.bootstrap = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bootstrap)
        self.desired = {"type":"bind","source":"/var/lib/reelio-updater-sockets/123456abcdef","target":"/run/reelio-updater","read_only":True,"bind":{"create_host_path":False}}
        self.config = {"services":{"api":{"image":"reelio/api:fixture","volumes":[{"type":"volume","source":"backups","target":"/backups"}]}}}

    def test_multi_file_keeps_disabled_ai_and_literal_secret_escaping(self):
        original = {"services":{"api":{"environment":{"SECRET":"literal$$value"}},"ai-worker":{"profiles":["disabled"]}},"volumes":{"reelio_ai_workspaces":None,"reelio_codex":{"external":True}}}
        result = self.bootstrap.updater_compose_document(self.config, json.dumps(original), True, self.desired, lambda _: self.fail("Existing JSON must not be escaped again"))
        self.assertEqual(result["services"]["ai-worker"],original["services"]["ai-worker"])
        self.assertEqual(result["volumes"],original["volumes"])
        self.assertEqual(result["services"]["api"]["environment"],original["services"]["api"]["environment"])
        self.assertEqual(result["services"]["api"]["volumes"],[self.desired])
        self.assertNotIn("image",result["services"]["api"])

    def test_single_file_keeps_existing_data_mount_and_escapes_once(self):
        helper=broker.load_helper()
        self.config["services"]["api"]["environment"]={"SECRET":"literal$value"}
        before=json.loads(json.dumps(self.config))
        result=self.bootstrap.updater_compose_document(self.config,b"unused YAML",False,self.desired,helper.escape_compose)
        self.assertEqual(result["services"]["api"]["environment"]["SECRET"],"literal$$value")
        self.assertEqual(result["services"]["api"]["volumes"],[before["services"]["api"]["volumes"][0],self.desired])
        self.assertEqual(self.config,before)

    def test_override_retains_reset_marker_and_original_mounts(self):
        original={"services":{"ai-worker":None,"api":{"volumes":[{"type":"bind","source":"/srv/custom","target":"/custom","read_only":True}]}},"volumes":{"reelio_codex":None}}
        result=self.bootstrap.updater_compose_document(self.config,json.dumps(original),True,self.desired,lambda _:self.fail("Unexpected escaping"))
        self.assertIsNone(result["services"]["ai-worker"])
        self.assertEqual(result["services"]["api"]["volumes"][0],original["services"]["api"]["volumes"][0])
        self.assertEqual(len(result["services"]["api"]["volumes"]),2)


if __name__ == "__main__":
    unittest.main()
