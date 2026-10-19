"""Run only against the disposable installation created by installer CI."""
import http.cookiejar
import json
from pathlib import Path
import secrets
import subprocess
import sys
import urllib.request

root = Path(sys.argv[1]).resolve()
assert root == Path("/opt/reelio-wizard-ci"), "Only the disposable CI installation is allowed"
config = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines()
              if line and not line.startswith("#"))
assert config["REELIO_BIND"] == "127.0.0.1"
assert config["REELIO_PORT"] == "43834"
assert config["REELIO_PROJECT"].startswith("reelio-wizard-ci-")
original = (root / ".env").read_bytes()
base = "http://127.0.0.1:" + config["REELIO_PORT"]
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=20) as response:
        return json.load(response)


assert call("/api/health")["version"] == (root / "VERSION").read_text().strip()
assert call("/api/setup/status")["needs_setup"] is True
password = secrets.token_hex(20)
(root / ".ci-owner.json").write_text(json.dumps({"email": "wizard@example.invalid", "password": password}))
(root / ".ci-owner.json").chmod(0o600)
assert call("/api/setup/owner", {"name": "Wizard test", "email": "wizard@example.invalid", "password": password})["id"]
call("/api/auth/login", {"email": "wizard@example.invalid", "password": password})
assert call("/api/me")["email"] == "wizard@example.invalid"
assert call("/api/requests") == []
# An accidental second fresh install must never overwrite its settings or data.
result = subprocess.run(["sh", str(root / "setup.sh")], env={
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "REELIO_NONINTERACTIVE": "1", "REELIO_ACCEPT_LICENSE": "1", "REELIO_INSTALL_DIR": str(root)},
    capture_output=True, text=True)
assert result.returncode != 0
assert original == (root / ".env").read_bytes()
assert call("/api/me")["email"] == "wizard@example.invalid"
subprocess.run(["sh", "backup.sh"], cwd=root, check=True)
assert (Path((root / ".last-backup").read_text().strip()) / "database.dump").stat().st_size > 0
assert original == (root / ".env").read_bytes()
print("Published bundle: healthy installation, owner/login, protected reinstall and verified backup passed.")
