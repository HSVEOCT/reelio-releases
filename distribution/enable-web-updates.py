#!/usr/bin/env python3
"""One-time, local owner authorization for the constrained update broker."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Verified bundles must stay byte-for-byte unchanged, including no .pyc files.
sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description="Enable Admin > Updates for this installation. Requires root and systemd once; later updates run in the browser.")
    parser.add_argument("--target", required=True, type=Path)
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0 or not Path("/run/systemd/system").is_dir():
        parser.error("Run once as the host administrator on Linux with systemd. The ordinary installer/updater remains available on other Docker hosts.")
    os.umask(0o077)
    target = args.target.resolve(strict=True)
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/_-." for character in str(target)):
        parser.error("This installation path is not supported by the service installer")
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("guided", source / "guided-update.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    installation = helper.Installation(target)
    if (target / "VERSION").read_text().strip() != installation.current:
        raise RuntimeError("Saved VERSION differs from the healthy API. Resolve this before enabling browser updates.")
    key = hashlib.sha256(str(target).encode()).hexdigest()[:12]
    protected = Path("/var/lib/reelio-updater") / key
    code = protected / "code"
    code.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Refuse paths controlled by an unprivileged user, including symlink parents.
    for path in [protected.parent, protected, code]:
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise RuntimeError("Updater directory must be root-owned and private")
    for name in ("reelio-updater.py", "guided-update.py", "reelio-telemetry.py"):
        destination = code / name
        if destination.is_symlink():
            raise RuntimeError("Updater code cannot be a symbolic link")
        shutil.copyfile(source / name, destination)
        destination.chmod(0o600)
    socket_dir = Path("/var/lib/reelio-updater-sockets") / key
    socket_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    for path in [socket_dir.parent, socket_dir]:
        if path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
            raise RuntimeError("Updater socket directory must be root-owned")
        path.chmod(0o755)
    unit = f"reelio-updater-{key}.service"
    unit_path = Path("/etc/systemd/system") / unit
    if unit_path.is_symlink():
        raise RuntimeError("Service unit cannot be a symbolic link")
    unit_path.write_text(f"""[Unit]
Description=Reelio browser updates ({key})
After=docker.service network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart={sys.executable} {code}/reelio-updater.py --target {target} --socket {socket_dir}/updater.sock --state {protected}/state.json --restart-after-update
Restart=on-failure
RestartSec=5
KillMode=process
TimeoutStopSec=600
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
""")
    unit_path.chmod(0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", unit], check=True)
    baseline = deepcopy(installation.config)
    retained_data = installation.snapshot()
    config = installation.config
    volumes = config["services"]["api"].setdefault("volumes", [])
    existing = [volume for volume in volumes if volume.get("target") == "/run/reelio-updater"]
    desired = {"type": "bind", "source": str(socket_dir), "target": "/run/reelio-updater", "read_only": True, "bind": {"create_host_path": False}}
    if existing and any(volume.get("source") != str(socket_dir) or not volume.get("read_only") for volume in existing):
        raise RuntimeError("An unexpected updater mount already exists")
    if not existing:
        original = installation.files[-1].read_bytes()
        backup = protected / "compose-before-enable"
        if not backup.exists():
            backup.write_bytes(original)
            backup.chmod(0o600)
        volumes.append(desired)
        try:
            helper.private_json(installation.files[-1], helper.escape_compose(config))
            planned=installation.compose_json()
            added=[volume for volume in planned["services"]["api"].get("volumes",[]) if volume.get("target")=="/run/reelio-updater"]
            if len(added)!=1 or added[0].get("source")!=str(socket_dir) or not added[0].get("read_only"):
                raise RuntimeError("Updater mount did not match the approved service")
            planned["services"]["api"]["volumes"]=[volume for volume in planned["services"]["api"]["volumes"] if volume.get("target")!="/run/reelio-updater"]
            if planned!=baseline:
                raise RuntimeError("Enabling updates would change unrelated application settings")
            installation.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "api")
            installation.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "180", "web")
            helper.retained(retained_data,installation.snapshot())
        except BaseException:
            installation.files[-1].write_bytes(original)
            installation.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "api")
            installation.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "180", "web")
            raise
    print("Browser updates enabled for this installation. Open Admin > Updates. The database and web port were retained.")


if __name__ == "__main__":
    main()
