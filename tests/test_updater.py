"""Pure updater rules; live-container coverage lives in smoke_update.py."""
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("updater", ROOT / "distribution/guided-update.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class UpdateRules(unittest.TestCase):
    def setUp(self):
        (ROOT / ".qa").mkdir(exist_ok=True)
        self.before = {"requests": ["request-1"], "users": {"owner": {"password_hash": "retain", "role": "admin"}},
                       "integrations": {"tmdb": {"api_key": "private fixture"}},
                       "settings": {"family": {"value": "retain"}}, "branding": {"1": {"accent": "#123456"}}}

    def test_original_records_must_survive_but_new_records_are_allowed(self):
        after = deepcopy(self.before)
        after["requests"].append("new-request")
        after["integrations"]["new-service"] = {"enabled": False}
        after["users"]["owner"]["new_default_column"] = False
        updater.retained(self.before, after)

    def test_missing_users_requests_or_changed_settings_fail(self):
        for table in self.before:
            with self.subTest(table=table):
                after = deepcopy(self.before)
                after[table] = [] if table == "requests" else {}
                with self.assertRaises(updater.UpdateError):
                    updater.retained(self.before, after)

    def test_credentials_and_permissions_cannot_silently_change(self):
        for table, key in (("users", "owner"), ("integrations", "tmdb"), ("branding", "1")):
            with self.subTest(table=table):
                after = deepcopy(self.before)
                after[table][key] = {"changed": True}
                with self.assertRaises(updater.UpdateError):
                    updater.retained(self.before, after)

    def test_only_application_image_selection_is_exempt_from_config_comparison(self):
        base = {"services": {"api": {"image": "old", "environment": {"SECURE_COOKIE": "true", "DATABASE_URL": "private"}},
                             "web": {"image": "old", "ports": [{"published": "8787"}]},
                             "postgres": {"image": "keep", "volumes": ["keep"]}}}
        expected = updater.without_application_images(base)
        changed = deepcopy(base)
        changed["services"]["api"]["image"] = "new"
        changed["services"]["web"]["pull_policy"] = "never"
        self.assertEqual(updater.without_application_images(changed), expected)
        for service, key, value in (("web", "ports", []), ("postgres", "image", "different"),
                                    ("api", "environment", {"DATABASE_URL": "different"})):
            changed = deepcopy(base)
            changed["services"][service][key] = value
            self.assertNotEqual(updater.without_application_images(changed), expected)

    def test_compose_literal_dollars_are_escaped_without_losing_other_values(self):
        self.assertEqual(updater.escape_compose({"environment": ["literal$money", "https://example.test"], "port": 8787}),
                         {"environment": ["literal$$money", "https://example.test"], "port": 8787})

    def test_rendered_compose_dollars_are_decoded_exactly_once(self):
        installation = updater.Installation.__new__(updater.Installation)
        installation.compose = lambda *args, **kwargs: json.dumps({"environment": {"ONE": "keep$$literal", "TWO": "keep$$$$literal"}})
        self.assertEqual(installation.compose_json()["environment"], {"ONE": "keep$literal", "TWO": "keep$$literal"})

    def test_semantic_versions_are_numeric_and_unambiguous(self):
        self.assertGreater(updater.version_tuple("1.0.17"), updater.version_tuple("1.0.9"))
        for invalid in (None, "latest", "v1.0.17", "1.0.17\n", "1.0.17;anything"):
            with self.assertRaises(updater.UpdateError):
                updater.version_tuple(invalid)

    def test_checksum_list_must_cover_all_payload_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".qa") as temporary:
            root = Path(temporary)
            (root / "web").mkdir()
            files = {"build.json": json.dumps({"packaging": "compiled-application", "platform": "linux/amd64"}),
                     "VERSION": "1.0.17\n", "image-tag.txt": "1.0.17-fixture\n", "prepare-images.sh": "fixture",
                     "api.Dockerfile": "fixture", "web.Dockerfile": "fixture", "reelio-api": "fixture", "web/index.html": "fixture"}
            for name, content in files.items():
                (root / name).write_text(content, newline="\n")
            checksums = "".join(hashlib.sha256(content.encode()).hexdigest() + "  " + name + "\n" for name, content in files.items())
            (root / "SHA256SUMS").write_text(checksums)
            self.assertEqual(updater.validate_bundle(root), "1.0.17")
            (root / "unexpected-secret.env").write_text("do not use")
            with self.assertRaises(updater.UpdateError):
                updater.validate_bundle(root)
            (root / "unexpected-secret.env").unlink()
            (root / "reelio-api").write_text("corrupted")
            with self.assertRaises(updater.UpdateError):
                updater.validate_bundle(root)

    def test_unexpected_release_hosts_and_preview_channels_are_refused(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".qa") as temporary:
            root = Path(temporary)
            for channel, url in (("preview", "https://example.test/app.tar.gz"),
                                 ("stable", "https://example.test/app.tar.gz")):
                data = {"version": "1.0.17", "channel": channel, "sha256": "a" * 64, "downloadUrl": url}
                def fixture_download(_url, path):
                    path.write_text(json.dumps(data))
                with patch.object(updater, "download", fixture_download), self.assertRaises(updater.UpdateError):
                    updater.stable_release(root)

    def test_original_mount_identity_is_compared_independently_of_order(self):
        a = {"Type": "volume", "Name": "data", "Source": "/data", "Destination": "/backups", "RW": True}
        b = {"Type": "bind", "Source": "/keep", "Destination": "/settings", "RW": False}
        self.assertEqual(updater.mounts({"Mounts": [a, b]}), updater.mounts({"Mounts": [b, a]}))
        changed = dict(a, Name="new-empty-volume")
        self.assertNotEqual(updater.mounts({"Mounts": [a]}), updater.mounts({"Mounts": [changed]}))

    def test_json_migration_override_keeps_all_other_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".qa") as temporary:
            target = Path(temporary)
            base, override = target / "docker-compose.yml", target / "docker-compose.override.yml"
            base.write_text("base")
            original = {"services": {"api": {"image": "old-api", "environment": {"SESSION_COOKIE": "home", "SECRET": "keep$$literal"}},
                                     "web": {"image": "old-web"}, "postgres": {"image": "fixed-digest"},
                                     "ai-worker": {"profiles": ["ai-disabled"], "restart": "no"}}}
            override.write_text(json.dumps(original))
            installation = updater.Installation.__new__(updater.Installation)
            installation.target = target
            installation.files = [base, override]
            installation.originals = {override: override.read_bytes()}
            installation.stage = None
            installation.config = {"services": {"api": {"image": "old"}, "web": {"image": "old"}}}
            installation.compose_json = lambda *_: deepcopy(installation.config)
            installation.plan("1.0.17-fixture")
            proposed = json.loads(installation.stage.read_text())
            self.assertEqual(override.read_bytes(), installation.originals[override])
            for name in ("api", "web"):
                proposed["services"][name]["image"] = original["services"][name]["image"]
                proposed["services"][name].pop("pull_policy")
            self.assertEqual(proposed, original)

    def test_failed_image_preparation_restores_original_tag_references(self):
        installation = updater.Installation.__new__(updater.Installation)
        installation.paused = False
        installation.prepared = True
        installation.config = {"services": {"api": {"image": "old-api"}, "web": {"image": "old-web"}}}
        installation.rows = {"api": {"Image": "sha256:old-api"}, "web": {"Image": "sha256:old-web"}}
        with patch.object(updater, "run") as command:
            installation.rollback()
        self.assertEqual(command.call_count, 2)
        self.assertIn("sha256:old-api", command.call_args_list[0].args[0])
        self.assertIn("old-web", command.call_args_list[1].args[0])

    def test_inactive_migration_volumes_without_labels_are_included(self):
        installation = updater.Installation.__new__(updater.Installation)
        installation.project = "legacy"
        installation.pg_mounts = [{"Type": "volume", "Name": "legacy-postgres"}]
        installation.rows = {"postgres": {"Id": "db", "Mounts": []}, "api": {"Id": "api", "Mounts": []}}
        installation.config = {"volumes": {"database": {"name": "legacy-postgres"}, "codex": {"name": "legacy-codex"}}}
        with patch.object(updater, "run", return_value=""), patch.object(updater, "docker_json", return_value=[{"Name": "legacy-codex"}]) as inspect:
            storage = installation.backup_storage()
        self.assertIn(("volume", "legacy-codex"), storage)
        self.assertNotIn(("volume", "legacy-postgres"), storage)
        inspect.assert_called_once_with("volume", "inspect", "legacy-codex")


if __name__ == "__main__":
    unittest.main(verbosity=2)
