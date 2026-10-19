#!/usr/bin/env python3
"""Optional Reelio install statistics. Standard library only; no account/media data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

ENDPOINT = "https://telemetry.harveyjs.uk"
STATE = ".reelio-telemetry.json"
HELPER = "reelio-telemetry.py"
DISABLED = ".reelio-telemetry.disabled"
OSES = {"ubuntu", "debian", "alpine", "fedora", "rhel", "centos", "rocky", "almalinux", "arch", "opensuse"}
ENVIRONMENTS = {"lxc", "kvm", "vmware", "docker", "podman", "oracle", "microsoft", "none"}


def switched_off():
    return os.environ.get("REELIO_TELEMETRY", "").lower() in {"0", "false", "off", "no"} or os.environ.get("DO_NOT_TRACK", "") == "1"


def disabled_marker(target):
    path = target / DISABLED
    return path.exists() or path.is_symlink()


def persist_disabled(target):
    try:
        descriptor = os.open(target / DISABLED, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    except FileExistsError:
        pass


def read_state(target):
    path = target / STATE
    if path.is_symlink():
        raise ValueError("Telemetry state must not be a symlink.")
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if data.get("schema") != 1 or type(data.get("enabled")) is not bool:
        raise ValueError("Unsupported telemetry settings.")
    return data


def save_state(target, state):
    temporary = target / (STATE + ".tmp")
    if temporary.is_symlink():
        raise ValueError("Unsafe telemetry state path.")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(state, output, indent=2)
        output.write("\n")
    os.chmod(temporary, 0o600)
    temporary.replace(target / STATE)


def command(args, timeout=8):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True)
    return result.stdout.strip()


def broad_platform():
    os_name = "other"
    try:
        match = re.search(r'^ID=["\']?([a-zA-Z0-9_-]+)', Path("/etc/os-release").read_text(), re.MULTILINE)
        if match and match[1] in OSES:
            os_name = match[1]
    except OSError:
        pass
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), "other")
    environment = "other"
    try:
        value = command(["systemd-detect-virt"], timeout=2)
        environment = value if value in ENVIRONMENTS else "other"
    except (OSError, subprocess.SubprocessError):
        # systemd-detect-virt exits 1 on bare metal.
        if shutil.which("systemd-detect-virt"):
            environment = "none"
    return {"os": os_name, "arch": architecture, "environment": environment}


def healthy_version(target, state):
    ids = command(["docker", "ps", "--filter", "label=com.docker.compose.project=" + state["project"], "--filter", "label=com.docker.compose.service=api", "--format", "{{.ID}}"]).splitlines()
    if len(ids) != 1:
        return None
    container = ids[0]
    details = json.loads(command(["docker", "inspect", container, "--format", '{{json .State}}']))
    if not details.get("Running") or details.get("Health", {}).get("Status") != "healthy":
        return None
    folder = command(["docker", "inspect", container, "--format", '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'])
    if Path(folder).resolve() != target:
        return None
    response = json.loads(command(["docker", "exec", container, "wget", "-qO-", "http://127.0.0.1:8080/api/health"], timeout=5))
    version = response.get("version", "")
    return version if re.fullmatch(r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}", version) else None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send(path, payload):
    request = urllib.request.Request(ENDPOINT + path, data=json.dumps(payload, separators=(",", ":")).encode(), headers={"Content-Type": "application/json", "User-Agent": "Reelio-Install-Statistics/1"}, method="POST")
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=4) as response:
        return 200 <= response.status < 300


def enqueue(state, event, version, day=None):
    day = day or datetime.now(timezone.utc).date().isoformat()
    identifier = hashlib.sha256((state["instance_id"] + ":" + event + ":" + version + (":" + day if event == "heartbeat" else "")).encode()).hexdigest()
    if identifier in state.get("sent", []) or any(row["event_id"] == identifier for row in state.get("pending", [])):
        return
    row = {"schema": 1, "instance_id": state["instance_id"], "instance_key": state["instance_key"], "event_id": identifier, "event": event, "version": version, "day": day, **broad_platform()}
    state.setdefault("pending", []).append(row)
    # Keep a bounded retry queue: earliest install/adoption plus recent events.
    state["pending"] = state["pending"][:1] + state["pending"][-7:] if len(state["pending"]) > 8 else state["pending"]


def flush(target, state):
    now = datetime.now(timezone.utc).date()
    pending = []
    # One bounded attempt per invocation; remaining reports wait for the next timer.
    for row in state.get("pending", []):
        age = (now - datetime.strptime(row["day"], "%Y-%m-%d").date()).days
        if 0 <= age <= 7:
            pending.append(row)
    state["pending"] = pending
    for row in list(pending)[:4]:
        try:
            accepted = send("/v1/events", row)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError):
            break
        if not accepted:
            break
        state["pending"].remove(row)
        state.setdefault("sent", []).append(row["event_id"])
        state["sent"] = state["sent"][-128:]
    save_state(target, state)


def unit_name(target):
    return "reelio-statistics-" + hashlib.sha256(str(target).encode()).hexdigest()[:12]


def timer(target, enabled):
    name = unit_name(target)
    if not Path("/run/systemd/system").exists() or not shutil.which("systemctl"):
        if enabled:
            print("Daily statistics need systemd. Installation reporting remains optional; no timer was created.")
        return False
    if not enabled:
        subprocess.run(["systemctl", "disable", "--now", name + ".timer"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        return True
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(target)) or "%" in str(target):
        print("Daily reporting was skipped for this installation path.")
        return False
    directory = Path("/etc/systemd/system")
    service = directory / (name + ".service")
    schedule = directory / (name + ".timer")
    if service.is_symlink() or schedule.is_symlink():
        raise ValueError("Unsafe statistics timer path.")
    service.write_text("[Unit]\nDescription=Optional Reelio installation statistics\nAfter=docker.service network-online.target\n\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 " + str(target / HELPER) + " report --target " + str(target) + "\nTimeoutStartSec=60\nUMask=0077\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nReadWritePaths=" + str(target) + "\nProtectHome=read-only\n")
    schedule.write_text("[Unit]\nDescription=Daily optional Reelio activity check\n\n[Timer]\nOnCalendar=daily\nRandomizedDelaySec=6h\nPersistent=true\nUnit=" + name + ".service\n\n[Install]\nWantedBy=timers.target\n")
    subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True, timeout=10)
    subprocess.run(["systemctl", "enable", "--now", name + ".timer"], check=True, capture_output=True, timeout=10)
    return True


def configure(target, project, event, version):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid reporting configuration.")
    previous = read_state(target)
    state = previous or {"schema": 1, "enabled": True, "project": project, "pending": [], "sent": []}
    state["project"] = project
    destination = target / HELPER
    if destination.is_symlink():
        raise ValueError("Unsafe statistics helper path.")
    if Path(__file__).resolve() != destination:
        shutil.copyfile(__file__, destination)
        os.chmod(destination, 0o644)
    if switched_off() or disabled_marker(target):
        state["enabled"] = False
    if not state["enabled"]:
        state["pending"] = []
        save_state(target, state)
        timer(target, False)
        print("Reelio installation statistics: disabled.")
        return
    if "instance_id" not in state:
        state.update(instance_id=str(uuid.uuid4()), instance_key=secrets.token_hex(32))
    save_state(target, state)
    try:
        timer(target, True)
    except (OSError, subprocess.SubprocessError, ValueError):
        print("Daily statistics timer could not be enabled. Reelio is unaffected.")
    if event == "adopt":
        actual = healthy_version(target, state)
        if not actual:
            print("Statistics configured; the daily timer will wait for a healthy Reelio API.")
            return
        version = actual
    if not previous and event == "update":
        enqueue(state, "adopt", version)
    enqueue(state, event, version)
    enqueue(state, "heartbeat", version)
    save_state(target, state)
    flush(target, state)
    print("Optional install statistics configured. Disable anytime with: sudo python3 " + str(destination) + " disable --target " + str(target))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "report", "disable", "enable", "status", "forget"])
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--project")
    parser.add_argument("--event", choices=["install", "update", "adopt"])
    parser.add_argument("--version")
    args = parser.parse_args()
    target = args.target.resolve(strict=True)
    if not target.is_dir() or target == Path(target.anchor):
        raise ValueError("Choose a Reelio installation directory.")
    if args.action == "configure":
        if not args.project or not args.event or not args.version:
            parser.error("configure needs --project, --event and --version")
        configure(target, args.project, args.event, args.version)
        return
    if args.action in {"disable", "forget"}:
        persist_disabled(target)
    state = read_state(target)
    if args.action == "status":
        print("Optional installation statistics: " + ("enabled" if state and state["enabled"] and not switched_off() and not disabled_marker(target) else "disabled"))
        return
    if not state:
        if args.action == "disable":
            save_state(target, {"schema": 1, "enabled": False, "pending": [], "sent": []})
        return
    if args.action in {"disable", "forget"}:
        state["enabled"] = False
        state["pending"] = []
        save_state(target, state)
        timer(target, False)
        print("Reelio installation statistics: disabled.")
        if args.action == "forget" and "instance_id" in state:
            if not send("/v1/forget", {key: state[key] for key in ["instance_id", "instance_key"]}):
                raise ValueError("Deletion was not confirmed. Reporting stays disabled; retry forget later.")
            for key in ["instance_id", "instance_key", "sent"]:
                state.pop(key, None)
            save_state(target, state)
            print("Installation record deleted. Anonymous aggregate totals are retained.")
        return
    if switched_off():
        return
    if args.action == "enable":
        if not state.get("project"):
            raise ValueError("Reporting needs a completed installation configuration first.")
        (target / DISABLED).unlink(missing_ok=True)
        state["enabled"] = True
        state.setdefault("instance_id", str(uuid.uuid4()))
        state.setdefault("instance_key", secrets.token_hex(32))
        save_state(target, state)
        timer(target, True)
    if not state["enabled"] or disabled_marker(target):
        return
    version = healthy_version(target, state)
    if version:
        enqueue(state, "heartbeat", version)
        save_state(target, state)
        flush(target, state)


if __name__ == "__main__":
    os.umask(0o077)
    try:
        # Prevent the daily timer and an updater from rewriting state concurrently.
        if sys.platform == "linux" and "--target" in sys.argv:
            import fcntl
            lock_target = Path(sys.argv[sys.argv.index("--target") + 1]).resolve(strict=True)
            lock_path = lock_target / ".reelio-telemetry.lock"
            if lock_path.is_symlink():
                raise ValueError("Unsafe statistics lock path.")
            with lock_path.open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    sys.exit(0)
                main()
        else:
            main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, urllib.error.URLError, TimeoutError):
        print("Optional statistics could not complete. Reelio is unaffected; disable or retry from the telemetry helper.", file=sys.stderr)
        sys.exit(0)
