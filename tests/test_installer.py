"""Exercise the real setup script with disposable files and fake host services."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SHELL = os.environ.get("REELIO_TEST_SHELL", "sh")


def shell_path(path):
    text = str(path).replace("\\", "/")
    if os.name == "nt" and len(text) > 2 and text[1] == ":":
        return "/" + text[0].lower() + text[2:]
    return text


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="reelio-wizard-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()
        self.target = self.root / "installed"
        self.log = self.root / "commands.log"
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith("REELIO_") or key in ("DOCKER_HOST", "DOCKER_CONTEXT"):
                self.env.pop(key)
        self.env.update(
            PATH=str(self.bin) + os.pathsep + self.env["PATH"],
            REELIO_NONINTERACTIVE="1", REELIO_ACCEPT_LICENSE="1",
            REELIO_INSTALL_DIR=shell_path(self.target), REELIO_ACCESS="3",
            FIXTURE=shell_path(self.fixture), MOCK_ROOT=shell_path(self.root),
            MOCK_LOG=shell_path(self.log),
        )
        if os.name == "nt":
            self.env["PATH"] = shell_path(self.bin) + ":/usr/bin:/bin"
        self.tool("uname", 'case "$1" in -s) echo Linux;; -m) echo x86_64;; esac')
        self.tool("id", "echo 0")
        self.tool("systemd-detect-virt", "echo none")
        self.tool("ip", '''case "$*" in
          *route*) echo '1.1.1.1 via 192.168.4.1 dev eth0 src 192.168.4.10';;
          *) printf '1: lo inet 127.0.0.1/8 scope host lo\\n2: eth0 inet 192.168.4.10/24 scope global eth0\\n';;
        esac''')
        self.tool("ss", '[ "${MOCK_PORT_BUSY:-0}" != 1 ] || echo LISTEN')
        self.tool("docker", '''printf '%s\\n' "$*" >> "$MOCK_LOG"
        case "$*" in
          info) [ "${MOCK_DOCKER_DOWN:-0}" != 1 ];;
          'info --format '*) echo "$MOCK_ROOT";;
          'context inspect '*) echo "${MOCK_ENDPOINT:-unix:///var/run/docker.sock}";;
          'ps -aq '*) [ "${MOCK_PROJECT_BUSY:-0}" != 1 ] || echo existing-container;;
          'ps --format '*) printf '%s' "${MOCK_PORT_MAPPING:-}";;
          'volume ls '*) [ "${MOCK_VOLUME_BUSY:-0}" != 1 ] || echo existing-volume;;
          'network ls '*) [ "${MOCK_NETWORK_BUSY:-0}" != 1 ] || echo existing-network;;
          'compose version') [ "${MOCK_COMPOSE_MISSING:-0}" != 1 ];;
          'compose --env-file .env up '*) [ "${MOCK_START_FAIL:-0}" != 1 ];;
          'compose --env-file .env config --quiet') :;;
          *) echo "Unexpected docker command: $*" >&2; exit 88;;
        esac''')
        self.tool("curl", '''url=''; dest=''
        while [ "$#" -gt 0 ]; do
          case "$1" in https://*) url=$1;; -o) shift; dest=$1;; esac
          shift
        done
        case "$url" in
          */site/release.json) cp "$FIXTURE/release.json" "$dest";;
          *.tar.gz.sha256) cp "$FIXTURE/archive.sha256" "$dest";;
          *.tar.gz) cp "$FIXTURE/archive.tar.gz" "$dest";;
          *) echo "Unexpected download: $url" >&2; exit 89;;
        esac''')
        files = {name: "fixture\n" for name in (
            ".env.example", "docker-compose.yml", "backup.sh", "update.sh", "LICENSE.txt")}
        files.update({"VERSION": "1.0.17\n", "image-tag.txt": "1.0.17-test\n",
                      "build.json": '{"packaging":"compiled-application"}\n',
                      "prepare-images.sh": '#!/bin/sh\nprintf prepared > prepared\n'})
        files["SHA256SUMS"] = "".join(
            hashlib.sha256(content.encode()).hexdigest() + "  " + name + "\n"
            for name, content in files.items())
        with tarfile.open(self.fixture / "archive.tar.gz", "w:gz") as archive:
            for name, content in files.items():
                data = content.encode()
                item = tarfile.TarInfo(name)
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
        digest = hashlib.sha256((self.fixture / "archive.tar.gz").read_bytes()).hexdigest()
        (self.fixture / "archive.sha256").write_text(digest + "  reelio-1.0.17-linux-amd64.tar.gz\n")
        (self.fixture / "release.json").write_text(json.dumps({"version": "1.0.17", "sha256": digest}, indent=2) + "\n")

    def tool(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\nset -eu\n" + body + "\n", newline="\n")
        path.chmod(0o755)

    def run_setup(self, *args, success=True, **changes):
        env = self.env | changes
        result = subprocess.run([SHELL, str(ROOT / "install.sh"), *args], env=env,
                                text=True, capture_output=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def config(self):
        return dict(line.split("=", 1) for line in (self.target / ".env").read_text().splitlines()
                    if line and not line.startswith("#"))

    def test_local_install_downloads_checks_and_starts(self):
        result = self.run_setup()
        config = self.config()
        self.assertEqual(config["REELIO_BIND"], "127.0.0.1")
        self.assertEqual(config["REELIO_PORT"], "43834")
        self.assertRegex(config["POSTGRES_PASSWORD"], r"^[a-f0-9]{64}$")
        self.assertTrue((self.target / "prepared").exists())
        self.assertFalse((self.target / ".reelio-setup-pending").exists())
        self.assertIn("http://127.0.0.1:43834", result.stdout)
        if os.name != "nt":
            self.assertEqual((self.target / ".env").stat().st_mode & 0o777, 0o600)

    def test_lan_detects_server_address(self):
        result = self.run_setup(REELIO_ACCESS="1", REELIO_PORT="43835")
        self.assertEqual(self.config()["REELIO_BIND"], "192.168.4.10")
        self.assertIn("http://192.168.4.10:43835", result.stdout)

    def test_https_proxy_saves_secure_settings(self):
        self.run_setup(REELIO_ACCESS="2", PUBLIC_URL="https://reelio.example.com/", TRUST_PROXY="y")
        config = self.config()
        self.assertEqual(config["PUBLIC_URL"], "https://reelio.example.com")
        self.assertEqual(config["SECURE_COOKIE"], "true")
        self.assertEqual(config["TRUST_PROXY"], "true")

    def test_proxy_headers_are_not_trusted_by_default(self):
        self.run_setup(REELIO_ACCESS="2", PUBLIC_URL="https://reelio.example.com")
        self.assertEqual(self.config()["TRUST_PROXY"], "false")

    def test_existing_directory_is_untouched(self):
        self.target.mkdir()
        original = self.target / ".env"
        original.write_text("keep this private data")
        self.run_setup(success=False)
        self.assertEqual(original.read_text(), "keep this private data")
        self.assertFalse(self.log.exists())

    def test_existing_project_is_untouched(self):
        self.run_setup(success=False, MOCK_PROJECT_BUSY="1")
        self.assertFalse(self.target.exists())

    def test_stopped_project_storage_is_not_reused(self):
        for values in ({"MOCK_VOLUME_BUSY": "1"}, {"MOCK_NETWORK_BUSY": "1"}):
            with self.subTest(values=values):
                self.run_setup(success=False, **values)
                self.assertFalse(self.target.exists())

    def test_listener_collision_is_rejected(self):
        self.run_setup(success=False, MOCK_PORT_BUSY="1")
        self.assertFalse(self.target.exists())

    def test_docker_port_collision_without_listener_is_rejected(self):
        self.run_setup(success=False, MOCK_PORT_MAPPING="0.0.0.0:43834->80/tcp, [::]:43834->80/tcp")
        self.assertFalse(self.target.exists())

    def test_invalid_and_foreign_bind_addresses_are_rejected(self):
        for address in ("0.0.0.0", "192.168.4.999", "192.168.4.50", "192.168.04.10", "$(touch bad)"):
            with self.subTest(address=address):
                self.run_setup(success=False, REELIO_ACCESS="1", REELIO_BIND=address)
                self.assertFalse(self.target.exists())

    def test_unattended_licence_acceptance_is_explicit(self):
        self.run_setup(success=False, REELIO_ACCEPT_LICENSE="0")
        self.assertFalse(self.target.exists())

    def test_invalid_proxy_url_cannot_inject_env_settings(self):
        self.run_setup(success=False, REELIO_ACCESS="2", PUBLIC_URL="https://example.com\nTRUST_PROXY=true")
        self.assertFalse(self.target.exists())

    def test_checksum_failure_does_not_install(self):
        with (self.fixture / "archive.tar.gz").open("ab") as stream:
            stream.write(b"corrupted")
        self.run_setup(success=False)
        self.assertFalse(self.target.exists())

    def test_verified_archive_still_rejects_unsafe_members(self):
        original = (self.fixture / "archive.tar.gz").read_bytes()
        for name, member_type in (("../escape", tarfile.REGTYPE), ("linked", tarfile.SYMTYPE)):
            with self.subTest(name=name):
                with tarfile.open(fileobj=io.BytesIO(original), mode="r:gz") as source:
                    with tarfile.open(self.fixture / "archive.tar.gz", "w:gz") as archive:
                        for item in source.getmembers():
                            archive.addfile(item, source.extractfile(item))
                        item = tarfile.TarInfo(name)
                        item.type = member_type
                        item.linkname = "../escape" if member_type == tarfile.SYMTYPE else ""
                        archive.addfile(item)
                digest = hashlib.sha256((self.fixture / "archive.tar.gz").read_bytes()).hexdigest()
                (self.fixture / "archive.sha256").write_text(digest + "  reelio-1.0.17-linux-amd64.tar.gz\n")
                (self.fixture / "release.json").write_text(json.dumps({"version": "1.0.17", "sha256": digest}, indent=2) + "\n")
                self.run_setup(success=False)
                self.assertFalse(self.target.exists())
                self.assertFalse((self.root / "escape").exists())

    def test_docker_failures_do_not_create_installation(self):
        for values in ({"MOCK_DOCKER_DOWN": "1"}, {"MOCK_COMPOSE_MISSING": "1"},
                       {"MOCK_ENDPOINT": "ssh://another-host"},
                       {"MOCK_ENDPOINT": "ssh://another-host", "DOCKER_CONTEXT": "remote", "DOCKER_HOST": "unix:///var/run/docker.sock"}):
            with self.subTest(values=values):
                self.run_setup(success=False, **values)
                self.assertFalse(self.target.exists())

    def test_failed_start_can_resume_without_changing_credentials(self):
        result = self.run_setup(success=False, MOCK_START_FAIL="1")
        before = (self.target / ".env").read_bytes()
        self.assertIn("--resume", result.stderr)
        self.run_setup("--resume", shell_path(self.target))
        self.assertEqual((self.target / ".env").read_bytes(), before)
        self.assertFalse((self.target / ".reelio-setup-pending").exists())

    def test_resume_refuses_an_existing_live_install(self):
        self.run_setup()
        self.run_setup("--resume", shell_path(self.target), success=False)

    @unittest.skipIf(os.name == "nt", "Controlling-terminal test runs on the Linux CI runner")
    def test_interactive_lan_defaults_and_licence_prompt(self):
        import fcntl
        import pty
        import select
        import termios
        master, slave = pty.openpty()

        def terminal():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        env = self.env | {"REELIO_NONINTERACTIVE": "0", "REELIO_ACCESS": "1", "REELIO_ACCEPT_LICENSE": "0"}
        child = subprocess.Popen([SHELL, str(ROOT / "install.sh")], stdin=slave, stdout=slave,
                                 stderr=slave, env=env, preexec_fn=terminal)
        os.close(slave)
        output = b""
        try:
            os.write(master, b"\n\n\n\n\ny\n")
            deadline = time.monotonic() + 30
            while child.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        output += os.read(master, 65536)
                    except OSError:
                        break
            self.assertEqual(child.wait(timeout=2), 0, output.decode(errors="replace"))
            self.assertEqual(self.config()["REELIO_BIND"], "192.168.4.10")
            self.assertIn(b"Do you accept", output)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            os.close(master)


if __name__ == "__main__":
    unittest.main(verbosity=2)
