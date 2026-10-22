#!/usr/bin/env python3
"""Host-only Reelio update broker. No TCP listener and no arbitrary commands.

Install beside a protected copy of guided-update.py. The web application gets
only the Unix socket, never the Docker socket or this service's files.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socketserver
import subprocess
import sys

# Verified bundles must stay byte-for-byte unchanged, including no .pyc files.
sys.dont_write_bytecode = True
import tempfile
import threading
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone


def load_helper():
    path = Path(__file__).with_name("guided-update.py")
    spec = importlib.util.spec_from_file_location("guided_update", path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper


class Broker:
    def __init__(self, target, state, helper=None, restart=False):
        self.target, self.state = Path(target), Path(state)
        self.restart=restart
        self.helper = helper or load_helper()
        self.lock = threading.Lock()
        self.result = {"phase": "idle"}
        if self.state.exists():
            self.result = json.loads(self.state.read_text())
            if self.result.get("phase") in {"checking", "downloading", "updating"}:
                self.result = {"phase": "attention", "message": "Updater restarted during an operation. Check the private backup and service health before retrying."}
                self.save()

    def save(self, **changes):
        self.result.update(changes, updated_at=datetime.now(timezone.utc).isoformat())
        temporary = self.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.result))
        temporary.chmod(0o600)
        temporary.replace(self.state)

    def current(self):
        return (self.target / "VERSION").read_text().strip()

    def status(self):
        return dict(self.result, enabled=True, version=self.current())

    def check(self):
        with tempfile.TemporaryDirectory(prefix="reelio-check-") as work:
            manifest = self.helper.stable_release(Path(work))
        # Return only a bounded allowlist from the official stable manifest.
        return {"version": manifest["version"], "sha256": manifest["sha256"],
                "available": self.helper.version_tuple(manifest["version"]) > self.helper.version_tuple(self.current())}

    def start(self, version, checksum):
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) or not re.fullmatch(r"[a-f0-9]{64}", checksum):
            raise ValueError("Invalid release confirmation")
        if not self.lock.acquire(blocking=False):
            raise ValueError("An update is already running")
        if self.result.get("phase") == "attention":
            self.lock.release()
            raise ValueError("The previous operation needs administrator attention")
        try:
            self.save(phase="checking", message="Checking the selected release", selected=version)
            threading.Thread(target=self.update, args=(version, checksum), daemon=False).start()
        except BaseException:
            self.lock.release()
            raise

    def update(self, version, checksum):
        restart=False
        try:
            with tempfile.TemporaryDirectory(prefix="reelio-button-") as work:
                manifest = self.helper.stable_release(Path(work))
                if (manifest["version"], manifest["sha256"]) != (version, checksum):
                    raise ValueError("The stable release changed. Check for updates again.")
                if self.helper.version_tuple(version) <= self.helper.version_tuple(self.current()):
                    raise ValueError("Only a newer stable release can be installed")
                self.save(phase="downloading", message="Downloading and verifying the official release")
                bundle = self.helper.release_bundle(manifest, Path(work))
                self.save(phase="updating", message="Preparing images, saving a private backup and updating Reelio. This page reconnects automatically.")
                # The protected helper performs preflight, directory locking, image
                # preparation, full backup, retention checks and application recovery.
                environment = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "LANG", "TZ"}}
                environment.update(REELIO_NONINTERACTIVE="1", REELIO_ACCEPT_LICENSE="1", REELIO_UPDATE_CONFIRM="1", PYTHONUNBUFFERED="1")
                with self.state.with_suffix(".log").open("w") as log:
                    os.chmod(log.name, 0o600)
                    result = subprocess.run([sys.executable, str(Path(__file__).with_name("guided-update.py")), "--target", str(self.target), "--bundle", str(bundle)], env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
                if result.returncode != 0:
                    self.save(phase="failed", message="Update did not pass. Automatic application recovery was attempted; inspect the private host log and backup before retrying.")
                elif self.current() != version:
                    self.save(phase="attention", message="The updater finished but the selected version could not be verified.")
                else:
                    self.save(phase="complete", message="Update verified. Existing data and settings retained.")
                    # Refresh only these verified distribution helpers. Protected
                    # code is never read from the application installation folder.
                    destination=Path(__file__).resolve().parent
                    for name in ("guided-update.py","reelio-updater.py","reelio-telemetry.py"):
                        source=bundle/name
                        if source.is_file() and source.resolve()!=destination/name:
                            temporary=destination/(name+".next")
                            shutil.copyfile(source,temporary)
                            temporary.chmod(0o600)
                            temporary.replace(destination/name)
                    restart=self.restart
        except Exception:
            self.save(phase="failed", message="Release verification or update failed. Your private host log contains recovery details.")
        finally:
            self.lock.release()
        if restart:
            os.execv(sys.executable,[sys.executable,*sys.argv])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/status":
            return self.respond(404, {"error": "Unknown operation"})
        self.respond(200, self.server.broker.status())

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size > 1024 or size < 2:
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(size))
            if self.path == "/check" and data == {}:
                return self.respond(200, self.server.broker.check())
            if self.path != "/update" or not isinstance(data, dict) or set(data) != {"version", "sha256"}:
                raise ValueError("Unknown operation")
            self.server.broker.start(data["version"], data["sha256"])
            self.respond(202, self.server.broker.status())
        except (ValueError, TypeError, KeyError):
            self.respond(409, {"error": "Operation refused. Refresh the update status and check the selected release."})
        except Exception:
            self.respond(503, {"error": "Official release check unavailable. Try again later."})


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--socket", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--restart-after-update",action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    args.socket.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    args.state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = open(args.state.with_suffix(".lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    args.socket.unlink(missing_ok=True)
    with Server(str(args.socket), Handler) as server:
        server.broker = Broker(args.target.resolve(strict=True), args.state,restart=args.restart_after_update)
        os.chown(args.socket, 10001, -1)
        args.socket.chmod(0o600)
        server.serve_forever()


if __name__ == "__main__":
    main()
