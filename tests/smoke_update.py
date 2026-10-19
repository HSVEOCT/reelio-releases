"""Live update/recovery checks, restricted to the disposable CI installation."""
from copy import deepcopy
import hashlib
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path(sys.argv[1]).resolve()
assert ROOT == Path("/opt/reelio-wizard-ci")
spec = importlib.util.spec_from_file_location("updater", SOURCE / "distribution/guided-update.py")
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)
config = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if line and not line.startswith("#"))
assert config["REELIO_PROJECT"].startswith("reelio-wizard-ci-")
ENV = os.environ | {"REELIO_NONINTERACTIVE": "1", "REELIO_ACCEPT_LICENSE": "1", "REELIO_UPDATE_CONFIRM": "1", "REELIO_REAPPLY": "1"}
original_env = (ROOT / ".env").read_bytes()
base = "http://127.0.0.1:" + config["REELIO_PORT"]
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
owner = json.loads((ROOT / ".ci-owner.json").read_text())
# The older backup helper starts services without waiting for their health
# checks. Establish a healthy baseline before invoking the strict updater.
updater.run(["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "--env-file", str(ROOT / ".env"),
             "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "api", "web"])


def call(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=20) as response:
        return json.load(response)


def update(*arguments, success=True):
    result = subprocess.run(["sh", str(SOURCE / "install.sh"), *arguments, str(ROOT)], env=ENV, capture_output=True, text=True, timeout=600)
    assert (result.returncode == 0) == success, result.stdout + result.stderr
    assert "private-fixture-key" not in result.stdout + result.stderr
    assert owner["password"] not in result.stdout + result.stderr
    return result


initial = updater.Installation(ROOT)
pg_id = initial.rows["postgres"]["Id"]
pg_image = initial.rows["postgres"]["Image"]
pg_mounts = updater.mounts(initial.rows["postgres"])
ports = initial.rows["web"]["HostConfig"]["PortBindings"]
call("/api/auth/login", owner)
owner_id = call("/api/me")["id"]
initial.sql("INSERT INTO requests(requested_by,requested_for,media_type,tmdb_id,title,status) SELECT id,id,'movie',42,'Retain update test','available' FROM users LIMIT 1")
initial.sql("UPDATE integrations SET api_key='private-fixture-key',enabled=false WHERE key='tmdb'")
initial.sql("INSERT INTO app_settings(key,value) VALUES('wizard-retained','{\"keep\":true}') ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value")
initial.sql("UPDATE site_branding SET site_name='Retained home branding',accent_color='#123456'")
updater.run(["docker", "exec", initial.rows["api"]["Id"], "sh", "-ec", "printf retained > /backups/wizard-marker"])
before = initial.snapshot()

with tempfile.TemporaryDirectory(prefix="reelio-update-smoke-") as temporary:
    fixture = Path(temporary) / "bad-version-bundle"
    fixture.mkdir()
    # Retain an exact payload copy before the installation's Compose file changes.
    names = [line.split("  ", 1)[1] for line in (ROOT / "SHA256SUMS").read_text().splitlines()]
    for name in names:
        destination = fixture / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    shutil.copy2(ROOT / "SHA256SUMS", fixture / "SHA256SUMS")
    saved_compose = (ROOT / "docker-compose.yml").read_bytes()
    update("--check")
    assert saved_compose == (ROOT / "docker-compose.yml").read_bytes()
    assert original_env == (ROOT / ".env").read_bytes()
    update("--update")
    current = updater.Installation(ROOT)
    updater.retained(before, current.snapshot())
    assert call("/api/me")["id"] == owner_id
    print("Public layout: existing session, requests, settings, PostgreSQL and backup data retained.")

    # Recreate only API/web with a legacy two-file JSON migration override.
    legacy = deepcopy(current.config)
    legacy["services"]["api"]["build"] = {"context": "./missing-private-api-source"}
    legacy["services"]["web"]["build"] = {"context": "./missing-private-web-source"}
    legacy["services"]["api"]["user"] = "reelio"
    legacy["services"]["api"]["environment"]["HOME_RETAIN_LITERAL"] = "keep$literal"
    legacy["services"]["api"]["environment"]["PUBLIC_URL"] = "http://reelio.example.invalid"
    for name in ("api", "web"):
        reference = f"reelio-update/{name}:legacy-{uuid.uuid4().hex[:8]}"
        updater.run(["docker", "image", "tag", current.rows[name]["Image"], reference])
        legacy["services"][name]["image"] = reference
        legacy["services"][name]["container_name"] = current.rows[name]["Name"].lstrip("/")
    extra_volume = config["REELIO_PROJECT"] + "_codex-fixture"
    updater.run(["docker", "volume", "create", "--label", "com.docker.compose.project=" + config["REELIO_PROJECT"], extra_volume])
    updater.run(["docker", "run", "--rm", "--network", "none", "--mount", f"type=volume,src={extra_volume},dst=/source", pg_image, "sh", "-ec", "printf preserved > /source/state"])
    legacy.setdefault("volumes", {})["codex-fixture"] = {"name": extra_volume}
    legacy["services"]["ai-worker"] = {"image": pg_image, "profiles": ["ai-disabled"], "restart": "no", "volumes": [{"type": "volume", "source": "codex-fixture", "target": "/codex"}]}
    updater.private_json(ROOT / "docker-compose.yml", updater.escape_compose(legacy))
    override = {"services": {"api": {"image": legacy["services"]["api"]["image"], "environment": legacy["services"]["api"]["environment"]},
                             "web": {"image": legacy["services"]["web"]["image"]},
                             "postgres": {"image": legacy["services"]["postgres"]["image"]},
                             "ai-worker": {"profiles": ["ai-disabled"], "restart": "no"}}, "x-home-migration": "preserve this"}
    override = updater.escape_compose(override)
    override_path = ROOT / "docker-compose.override.yml"
    updater.private_json(override_path, override)
    updater.run(["docker", "compose", "-p", config["REELIO_PROJECT"], "-f", str(ROOT / "docker-compose.yml"), "-f", str(override_path), "--env-file", str(ROOT / ".env"),
                 "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "api", "web"])
    legacy_base = (ROOT / "docker-compose.yml").read_bytes()
    update("--check")
    update("--update")
    current = updater.Installation(ROOT)
    assert (ROOT / "docker-compose.yml").read_bytes() == legacy_base
    modified = json.loads(override_path.read_text())
    for name in ("api", "web"):
        modified["services"][name]["image"] = override["services"][name]["image"]
        modified["services"][name].pop("pull_policy", None)
    assert modified == override
    assert updater.environment(current.rows["api"])["HOME_RETAIN_LITERAL"] == "keep$literal"
    assert "ai-worker" not in current.rows
    assert updater.run(["docker", "run", "--rm", "--network", "none", "--mount", f"type=volume,src={extra_volume},dst=/source,readonly", pg_image, "cat", "/source/state"]) == "preserved"
    updater.retained(before, current.snapshot())
    assert call("/api/me")["id"] == owner_id
    print("Legacy layout: JSON override, literal-dollar settings, old build paths, disabled worker and independent data volumes retained.")

    # Advertise a newer version while retaining the current binary, even after
    # the stable release advances beyond the version this test first used.
    # This must fail the post-start version check and restore the old deployment.
    major, minor, patch = updater.version_tuple(current.current)
    rollback_version = f"{major}.{minor}.{patch + 1}"
    (fixture / "VERSION").write_text(rollback_version + "\n")
    (fixture / "image-tag.txt").write_text("rollback-test-" + uuid.uuid4().hex[:8] + "\n")
    metadata = json.loads((fixture / "build.json").read_text())
    metadata["version"] = rollback_version
    updater.private_json(fixture / "build.json", metadata)
    (fixture / "SHA256SUMS").write_text("".join(updater.digest(fixture / name) + "  " + name + "\n" for name in names))
    old_files = {path: path.read_bytes() for path in current.files}
    old_ids = {name: current.rows[name]["Image"] for name in ("api", "web")}
    result = subprocess.run(["python3", str(SOURCE / "distribution/guided-update.py"), "--target", str(ROOT), "--bundle", str(fixture)],
                            env=ENV, text=True, capture_output=True, timeout=600)
    assert result.returncode != 0, "The wrong-version fixture was accepted"
    assert "unexpected version" in result.stderr
    assert "NOT automatically restored" in result.stderr
    assert "private-fixture-key" not in result.stdout + result.stderr
    current = updater.Installation(ROOT)
    assert all(path.read_bytes() == content for path, content in old_files.items())
    assert all(current.rows[name]["Image"] == value for name, value in old_ids.items())
    assert call("/api/me")["id"] == owner_id
    updater.retained(before, current.snapshot())
    assert original_env == (ROOT / ".env").read_bytes()
    assert current.rows["postgres"]["Id"] == pg_id and current.rows["postgres"]["Image"] == pg_image
    assert updater.mounts(current.rows["postgres"]) == pg_mounts
    assert current.rows["web"]["HostConfig"]["PortBindings"] == ports
    assert updater.run(["docker", "exec", current.rows["api"]["Id"], "cat", "/backups/wizard-marker"]) == "retained"
    backup_parent = ROOT.parent / f".{ROOT.name}-reelio-backups"
    backups = list(backup_parent.iterdir())
    assert len(backups) == 3
    assert all((item / "verified.json").is_file() and (item / "images.tar.gz").is_file() for item in backups)
    assert sum((item / "update-passed.json").exists() for item in backups) == 2
    print("Failed-version rollback: previous images, configuration, live session and data recovered; database was never restored or recreated.")
