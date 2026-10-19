#!/usr/bin/env python3
"""Guided updates for local, single-instance Reelio Compose deployments.

This is a public distribution helper, not application source. Never print the
rendered Compose configuration, Docker environment, or database snapshots.
"""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:  # Unit checks may run on Windows; deployment is Linux-only.
    fcntl = None
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import unquote, urlparse
from urllib.request import urlopen
import uuid


REPOSITORY = "https://github.com/HSVEOCT/reelio-releases"
MANIFEST = "https://raw.githubusercontent.com/HSVEOCT/reelio-releases/main/site/release.json"
CORE_SQL = """SELECT jsonb_build_object(
 'users',(SELECT COALESCE(jsonb_object_agg(id::text,to_jsonb(t)-'updated_at'-'last_login_at'),'{}') FROM users t),
 'requests',(SELECT COALESCE(jsonb_agg(id::text ORDER BY id),'[]') FROM requests),
 'integrations',(SELECT COALESCE(jsonb_object_agg(key,to_jsonb(t)-'updated_at'),'{}') FROM integrations t),
 'settings',(SELECT COALESCE(jsonb_object_agg(key,value),'{}') FROM app_settings),
 'branding',(SELECT COALESCE(jsonb_object_agg(id::text,to_jsonb(t)-'updated_at'),'{}') FROM site_branding t));"""


class UpdateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise UpdateError(message)


def run(args, *, label="Docker command", input_file=None, output_file=None):
    result = subprocess.run(args, stdin=input_file, stdout=output_file or subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    require(result.returncode == 0, f"{label} failed. Existing credentials are omitted from this message.")
    return result.stdout.decode() if output_file is None else ""


def docker_json(*args):
    return json.loads(run(["docker", *args]))


def private_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.chmod(0o600)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def version_tuple(text):
    require(isinstance(text, str) and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", text), "The application version is not supported by guided updates.")
    return tuple(map(int, text.split(".")))


def download(url, path):
    require(url.startswith("https://"), "Downloads require HTTPS.")
    try:
        with urlopen(url, timeout=60) as response, path.open("wb") as destination:
            require(response.geturl().startswith("https://"), "An insecure download redirect was refused.")
            shutil.copyfileobj(response, destination)
    except (OSError, ValueError) as error:
        raise UpdateError("Could not download the release. Check GitHub connectivity and available disk space.") from error


def stable_release(work):
    path = work / "release.json"
    download(MANIFEST, path)
    manifest = json.loads(path.read_text())
    version_tuple(manifest.get("version"))
    require(manifest.get("channel") == "stable", "There is no stable release selected.")
    require(re.fullmatch(r"[a-f0-9]{64}", manifest.get("sha256", "")), "The stable release checksum is missing.")
    name = f"reelio-{manifest['version']}-linux-amd64.tar.gz"
    expected_url = f"{REPOSITORY}/releases/download/v{manifest['version']}/{name}"
    require(manifest.get("downloadUrl") == expected_url, "The stable download address is unexpected.")
    return manifest


def validate_bundle(bundle, expected_version=None):
    required = ("SHA256SUMS", "build.json", "VERSION", "image-tag.txt", "prepare-images.sh",
                "api.Dockerfile", "web.Dockerfile", "reelio-api", "web/index.html")
    require(all((bundle / name).is_file() for name in required), "This is not a complete compiled application bundle.")
    metadata = json.loads((bundle / "build.json").read_text())
    require(metadata.get("packaging") == "compiled-application" and metadata.get("platform") == "linux/amd64", "The release packaging/platform is not supported.")
    version = (bundle / "VERSION").read_text().strip()
    version_tuple(version)
    require(not expected_version or version == expected_version, "The bundle version does not match the stable release.")
    require(re.fullmatch(r"[a-zA-Z0-9._-]+", (bundle / "image-tag.txt").read_text().strip()), "The release image tag is invalid.")
    listed = set()
    for line in (bundle / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  ([a-zA-Z0-9_./-]+)", line)
        require(match is not None, "The application checksum list is invalid.")
        name = match[2]
        path = bundle / name
        require(not path.is_symlink() and path.resolve().is_relative_to(bundle.resolve()) and path.is_file(), "The bundle contains an unsafe file.")
        require(digest(path) == match[1], f"Application file verification failed: {name}")
        listed.add(name)
    require(set(required) - {"SHA256SUMS"} <= listed, "Required application files are not covered by checksums.")
    for path in bundle.rglob("*"):
        require(not path.is_symlink(), "Bundle links are not supported.")
        if path.is_file():
            require(path.relative_to(bundle).as_posix() in listed | {"SHA256SUMS"}, "The bundle contains an unverified file.")
    return version


def release_bundle(manifest, work):
    archive = work / "release.tar.gz"
    checksum = work / "release.sha256"
    download(manifest["downloadUrl"], archive)
    download(manifest["downloadUrl"] + ".sha256", checksum)
    require(digest(archive) == manifest["sha256"], "The downloaded archive failed its checksum. Nothing was updated.")
    name = manifest["downloadUrl"].rsplit("/", 1)[1]
    require(checksum.read_text().strip() == f"{manifest['sha256']}  {name}", "The release checksum file is inconsistent.")
    bundle = work / "bundle"
    bundle.mkdir(mode=0o700)
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        names = set()
        for member in members:
            path = Path(member.name)
            require(not path.is_absolute() and ".." not in path.parts and re.fullmatch(r"[a-zA-Z0-9_./-]+", member.name), "The archive contains an unsafe path.")
            require(member.isfile() or member.isdir(), "The archive contains a link or special file.")
            require(member.name not in names, "The archive contains duplicate members.")
            names.add(member.name)
        # Explicitly materialize regular files/directories; do not use extractall.
        for member in members:
            path = bundle / member.name
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                path.chmod(0o755)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as data, path.open("wb") as destination:
                    shutil.copyfileobj(data, destination)
                path.chmod(0o755 if member.mode & 0o111 else 0o644)
        for path in bundle.rglob("*"):
            if path.is_dir():
                path.chmod(0o755)
    validate_bundle(bundle, manifest["version"])
    return bundle


def environment(container):
    return dict(item.split("=", 1) for item in container["Config"].get("Env", []) if "=" in item)


def mounts(container):
    return sorted(({key: item.get(key) for key in ("Type", "Name", "Source", "Destination", "RW")}
                   for item in container.get("Mounts", [])), key=lambda item: item["Destination"])


def retained(before, after):
    require(set(before["requests"]) <= set(after["requests"]), "Original request IDs are missing after the update.")
    for table in ("users", "integrations", "settings", "branding"):
        for key, value in before[table].items():
            require(key in after[table], f"Original {table} did not pass the retention check.")
            current = after[table][key]
            if table != "settings":
                require(isinstance(current, dict) and all(field in current and current[field] == data for field, data in value.items()),
                        f"Original {table} did not pass the retention check.")
            else:
                require(current == value, "Original settings did not pass the retention check.")


def escape_compose(data):
    if isinstance(data, str):
        return data.replace("$", "$$")
    if isinstance(data, list):
        return [escape_compose(item) for item in data]
    if isinstance(data, dict):
        return {key: escape_compose(value) for key, value in data.items()}
    return data


def without_application_images(config):
    result = deepcopy(config)
    for service in ("api", "web"):
        result["services"][service].pop("image", None)
        result["services"][service].pop("pull_policy", None)
    return result


def ask(question, default="n"):
    require(os.environ.get("REELIO_NONINTERACTIVE") != "1", "Unattended updates need explicit confirmation settings.")
    try:
        # Buffered update mode (r+) requires seeking; Linux terminals cannot seek.
        with open("/dev/tty", "r", encoding="utf-8") as reader, open("/dev/tty", "w", encoding="utf-8") as writer:
            writer.write(f"{question} [{default}]: ")
            writer.flush()
            reply = reader.readline()
    except OSError as error:
        raise UpdateError("Could not read the confirmation terminal. Run the updater from an interactive server console or SSH session.") from error
    require(reply != "", "Update cancelled: terminal closed.")
    return reply.strip() or default


def candidates():
    ids = run(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.service=api"]).split()
    rows = docker_json("inspect", *ids) if ids else []
    return [row for row in rows if row["Config"].get("Labels", {}).get("com.docker.compose.project.working_dir")]


def select_target(target):
    if target:
        return Path(target).resolve(strict=True)
    rows = candidates()
    choices = sorted({row["Config"]["Labels"]["com.docker.compose.project.working_dir"] for row in rows})
    require(choices, "No Reelio Compose installation was found. Choose a folder explicitly with --update /path/to/reelio.")
    if len(choices) == 1:
        return Path(choices[0]).resolve(strict=True)
    print("Existing installations:")
    for index, path in enumerate(choices, 1):
        print(f"  {index}) {path}")
    choice = ask("Which installation should be updated? Enter its number", "")
    require(choice.isdigit() and 1 <= int(choice) <= len(choices), "Choose a valid installation number.")
    return Path(choices[int(choice) - 1]).resolve(strict=True)


class Installation:
    def __init__(self, target):
        self.target = target
        require(target.is_dir() and target != Path("/"), "Choose an existing installation directory.")
        matches = [row for row in candidates() if Path(row["Config"]["Labels"]["com.docker.compose.project.working_dir"]).resolve() == target]
        require(len(matches) == 1, "Expected one API container belonging to this directory. Nothing was changed.")
        labels = matches[0]["Config"]["Labels"]
        self.project = labels["com.docker.compose.project"]
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.project), "The existing project name is invalid.")
        self.files = [Path(name).resolve(strict=True) for name in labels.get("com.docker.compose.project.config_files", "").split(",") if name]
        require(self.files and all(path.is_relative_to(target) and path.is_file() and not path.is_symlink() for path in self.files), "All Compose files must be ordinary files inside the selected installation directory.")
        self.originals = {path: path.read_bytes() for path in self.files}
        if len(self.files) > 1:
            try:
                json.loads(self.originals[self.files[-1]])
            except (ValueError, UnicodeError) as error:
                raise UpdateError("This custom layout has a YAML override. Guided custom updates currently support the captured JSON migration override; no files were changed.") from error
        self.env_path = target / ".env"
        self.env_original = self.env_path.read_bytes() if self.env_path.exists() else None
        self.config = self.compose_json()
        require(all(name in self.config.get("services", {}) for name in ("api", "web", "postgres")), "This layout needs api, web and postgres services.")
        self.rows = self.inspect()
        for name in ("api", "web", "postgres"):
            row = self.rows[name]
            require(row["State"].get("Running") and row["State"].get("Health", {}).get("Status") == "healthy", f"The existing {name} service must be healthy before updating.")
            for key, value in self.config["services"][name].get("environment", {}).items():
                require(value is not None and environment(row).get(key) == str(value), f"Saved {name} settings differ from the running service. Apply or resolve those changes first.")
            reference = self.config["services"][name].get("image")
            require(reference and docker_json("image", "inspect", reference)[0]["Id"] == row["Image"], f"The saved {name} image differs from the running image. Resolve this before updating.")
        require(not any(row["State"].get("Running") for name, row in self.rows.items() if name not in ("api", "web", "postgres")), "Other services are running in this Compose project. Stop its optional workers before updating; their data will be retained.")
        pg_env = environment(self.rows["postgres"])
        url = urlparse(environment(self.rows["api"]).get("DATABASE_URL", ""))
        aliases = {"postgres", self.rows["postgres"]["Name"].lstrip("/")}
        for network in self.rows["postgres"].get("NetworkSettings", {}).get("Networks", {}).values():
            aliases.update(network.get("Aliases") or [])
        require(url.scheme in ("postgres", "postgresql") and url.hostname in aliases and url.port in (None, 5432), "External or ambiguous database connections require a separately planned update.")
        require(unquote(url.path.lstrip("/")) == pg_env.get("POSTGRES_DB", pg_env.get("POSTGRES_USER", "postgres")) and unquote(url.username or "") == pg_env.get("POSTGRES_USER", "postgres"), "The API and PostgreSQL database identity do not match.")
        pg_version = int(self.sql("SHOW server_version_num").strip())
        require(180000 <= pg_version < 190000, "Guided updates currently support PostgreSQL 18 only; database major versions are never changed.")
        self.pg_mounts = mounts(self.rows["postgres"])
        require(any(item["Type"] == "volume" and item["Destination"].startswith("/var/lib/postgresql") for item in self.pg_mounts)
                and not any(item["Type"] == "bind" and item["Destination"].startswith("/var/lib/postgresql") for item in self.pg_mounts),
                "Guided updates require PostgreSQL data in a Docker named volume. Bind-mounted databases need separate review.")
        self.current = self.health_version()
        require(version_tuple(self.current) >= (1, 0, 14), "This older application needs a separately planned migration.")
        self.stage = None
        self.backup = None
        self.paused = False
        self.changed = False
        self.prepared = False
        self.data_failed = False
        self.rollback_tags = {}
        self.old_metadata = {name: (target / name).read_bytes() if (target / name).exists() else None for name in ("VERSION", "image-tag.txt")}

    def command(self, files=None):
        args = ["docker", "compose", "--project-directory", str(self.target), "-p", self.project]
        for path in files or self.files:
            args += ["-f", str(path)]
        if self.env_original is not None:
            args += ["--env-file", str(self.env_path)]
        return args

    def compose(self, *args, files=None):
        return run(self.command(files) + list(args), label="Compose operation")

    def compose_json(self, files=None):
        # Compose's config command doubles every literal dollar in its rendered
        # JSON for reuse as a Compose file. Undo exactly that rendering layer
        # before comparing to live environment values or serializing again.
        return json.loads(self.compose("config", "--format", "json", files=files).replace("$$", "$"))

    def inspect(self):
        ids = run(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={self.project}"]).split()
        rows = docker_json("inspect", *ids) if ids else []
        services = {}
        for row in rows:
            service = row["Config"].get("Labels", {}).get("com.docker.compose.service")
            require(service and service not in services, "Multiple containers for one service are not supported by this updater.")
            services[service] = row
        require(all(name in services for name in ("api", "web", "postgres")), "Expected existing API, web and PostgreSQL containers.")
        return services

    def sql(self, sql):
        return run(["docker", "exec", self.rows["postgres"]["Id"], "sh", "-ec",
                    'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -c "$1"', "sh", sql], label="Database inspection")

    def snapshot(self):
        return json.loads(self.sql(CORE_SQL))

    def health_version(self):
        data = json.loads(run(["docker", "exec", self.rows["api"]["Id"], "wget", "-qO-", "http://127.0.0.1:8080/api/health"], label="Application version check"))
        version_tuple(data.get("version"))
        return data["version"]

    def summary(self, selected):
        print(f"\nInstallation: {self.target}\nProject: {self.project}\nCurrent version: {self.current}\nSelected stable version: {selected}")
        ports = self.rows["web"].get("NetworkSettings", {}).get("Ports", {}).get("80/tcp") or []
        for port in ports:
            print(f"Keep web address/port: {port['HostIp']}:{port['HostPort']}")
        public = environment(self.rows["api"]).get("PUBLIC_URL", "")
        if public and re.fullmatch(r"https?://[a-zA-Z0-9.:/-]+", public):
            print(f"Keep public URL: {public}")
        print("Database container, PostgreSQL image, storage, credentials and other services stay in place.")

    def plan(self, tag):
        if self.stage:
            self.stage.unlink(missing_ok=True)
        last = self.files[-1]
        if len(self.files) == 1:
            data = escape_compose(self.config)
        else:
            try:
                data = json.loads(self.originals[last])
            except (ValueError, UnicodeError) as error:
                raise UpdateError("This custom layout has a YAML override. Guided custom updates currently support the captured JSON migration override; no files were changed.") from error
        for name in ("api", "web"):
            service = data.setdefault("services", {}).setdefault(name, {})
            service["image"] = f"reelio/{name}:{tag}"
            service["pull_policy"] = "never"
        fd, filename = tempfile.mkstemp(prefix=".reelio-update-", suffix=".json", dir=self.target)
        os.close(fd)
        self.stage = Path(filename)
        private_json(self.stage, data)
        planned = self.compose_json(self.files[:-1] + [self.stage])
        require(without_application_images(planned) == without_application_images(self.config), "The proposed update would change settings beyond the API/web images. Nothing was changed.")

    def verify_unchanged(self):
        require(all(path.read_bytes() == content for path, content in self.originals.items()), "Compose files changed while preparing the update. Rerun after resolving concurrent edits.")
        current_env = self.env_path.read_bytes() if self.env_path.exists() else None
        require(current_env == self.env_original, "The private environment changed while preparing the update.")
        now = self.inspect()
        for name in ("api", "web", "postgres"):
            require(now[name]["Id"] == self.rows[name]["Id"] and now[name]["Image"] == self.rows[name]["Image"], "The running deployment changed while preparing the update.")

    def backup_storage(self):
        database_volumes = {item["Name"] for item in self.pg_mounts if item["Type"] == "volume"}
        selected = {}
        for row in self.rows.values():
            for mount in row.get("Mounts", []):
                if row["Id"] == self.rows["postgres"]["Id"]:
                    continue
                if mount["Type"] == "volume" and mount.get("Name") not in database_volumes:
                    selected[("volume", mount["Name"])] = mount
                elif mount["Type"] == "bind":
                    selected[("bind", mount["Source"])] = mount
        names = run(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={self.project}"]).split()
        for name in names:
            if name not in database_volumes:
                selected.setdefault(("volume", name), {"Type": "volume", "Name": name, "Destination": None})
        # Migration restores may have created declared volumes by name without
        # Compose labels. Include existing, inactive storage too; never create it.
        for definition in self.config.get("volumes", {}).values():
            name = definition.get("name")
            if not name or name in database_volumes or ("volume", name) in selected:
                continue
            try:
                docker_json("volume", "inspect", name)
            except UpdateError:
                continue
            selected[("volume", name)] = {"Type": "volume", "Name": name, "Destination": None}
        for kind, source in selected:
            require("," not in source and "\n" not in source, "A data mount path needs a separately planned backup.")
        return selected

    def storage_command(self, kind, source, command):
        return ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
                "--mount", f"type={kind},src={source},dst=/source,readonly", self.rows["postgres"]["Image"], "sh", "-ec", command]

    def create_backup(self, storage):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        parent = self.target.parent / f".{self.target.name}-reelio-backups"
        require(not parent.is_symlink(), "The backup directory must not be a symlink.")
        parent.mkdir(mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        require(not parent.resolve().is_relative_to(self.target), "Backups must be outside the installation folder.")
        image_rows = docker_json("image", "inspect", *sorted({self.rows[name]["Image"] for name in ("api", "web", "postgres")}))
        estimate = int(self.sql("SELECT pg_database_size(current_database())").strip()) * 2
        estimate += sum(row["Size"] for row in image_rows)
        estimate += sum(path.stat().st_size for path in self.target.rglob("*") if path.is_file() and not path.is_symlink())
        for kind, source in storage:
            size = run(self.storage_command(kind, source, "du -sk /source"), label="Persistent storage size check").split()[0]
            estimate += int(size) * 1024
        require(shutil.disk_usage(parent).free > estimate + 256 * 1024 * 1024, "Not enough free space for the database, application files, old images and data-volume backups.")
        self.backup = parent / stamp
        self.backup.mkdir(mode=0o700)
        private_json(self.backup / "containers.json", self.rows)
        private_json(self.backup / "compose-resolved.json", self.config)
        private_json(self.backup / "storage.json", [{"archive": f"storage-{index}.tar.gz", "type": kind, "source": source, "mount": value} for index, ((kind, source), value) in enumerate(storage.items())])
        for name in ("api", "web", "postgres"):
            tag = f"reelio-rollback/{name}:{stamp.lower()}"
            run(["docker", "image", "tag", self.rows[name]["Image"], tag], label="Retaining previous images")
            self.rollback_tags[name] = tag
        # Save images while the old app remains online; no lengthy build or
        # image export belongs in the application downtime window.
        process = subprocess.Popen(["docker", "image", "save", *self.rollback_tags.values()], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            with gzip.open(self.backup / "images.tar.gz", "wb") as destination:
                shutil.copyfileobj(process.stdout, destination)
        finally:
            process.stdout.close()
            status = process.wait()
        require(status == 0, "Could not save the previous images. The application was left running.")
        with tarfile.open(self.backup / "images.tar.gz", "r:gz") as archive:
            require(archive.getmember("manifest.json").isfile(), "The image backup is invalid.")
            archive.getmembers()
        with tarfile.open(self.backup / "application.tar.gz", "w:gz", dereference=False) as archive:
            archive.add(self.target, arcname=self.target.name, filter=lambda member: None if "/.reelio-update-" in member.name else member)
        print(f"\nPrevious images and configuration saved. Pausing API/web for the final database and data backup...\nPrivate backup folder: {self.backup}")
        self.paused = True
        self.compose("stop", "--timeout", "60", "web", "api")
        self.before = self.snapshot()
        private_json(self.backup / "data-before.json", self.before)
        with (self.backup / "database.dump").open("wb") as destination:
            run(["docker", "exec", self.rows["postgres"]["Id"], "sh", "-ec", 'exec pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-${POSTGRES_USER:-postgres}}" -Fc'], output_file=destination, label="Database backup")
        with (self.backup / "database.dump").open("rb") as source:
            run(["docker", "exec", "-i", self.rows["postgres"]["Id"], "pg_restore", "--file=/dev/null"], input_file=source, label="Reading and verifying the complete database backup")
        for index, ((kind, source), _) in enumerate(storage.items()):
            with (self.backup / f"storage-{index}.tar.gz").open("wb") as destination:
                run(self.storage_command(kind, source, "if [ -d /source ]; then tar -czf - -C /source .; else tar -czf - -C / source; fi"), output_file=destination, label="Persistent data backup")
            with tarfile.open(self.backup / f"storage-{index}.tar.gz", "r:gz") as archive:
                archive.getmembers()
        private_json(self.backup / "verified.json", {"version": self.current, "project": self.project, "imageTags": self.rollback_tags,
                     "files": {path.name: digest(path) for path in self.backup.iterdir() if path.is_file()}})
        print(f"Backup verified. Retaining {len(self.before['users'])} users and {len(self.before['requests'])} requests.")

    def check_new_backup_permissions(self, tag):
        directory = environment(self.rows["api"]).get("BACKUP_DIR", "/backups")
        data_mount = next((item for item in self.rows["api"].get("Mounts", []) if item["Destination"] == directory), None)
        require(data_mount and data_mount["Type"] in ("volume", "bind") and data_mount["RW"], "The API backup directory needs a supported writable persistent mount.")
        source = data_mount.get("Name") if data_mount["Type"] == "volume" else data_mount["Source"]
        require("," not in source and "," not in directory, "The backup mount path needs manual review.")
        args = ["docker", "run", "--rm", "--network", "none", "--read-only"]
        if self.config["services"]["api"].get("user"):
            args += ["--user", self.config["services"]["api"]["user"]]
        args += ["--mount", f"type={data_mount['Type']},src={source},dst={directory}", "--entrypoint", "sh", f"reelio/api:{tag}", "-ec", 'test -w "$1"', "sh", directory]
        run(args, label="New application backup-directory permission check (no permissions were changed)")

    def apply(self, version, tag):
        self.verify_unchanged()
        self.changed = True
        self.stage.replace(self.files[-1])
        self.stage = None
        self.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "api")
        after = self.snapshot()
        private_json(self.backup / "data-after.json", after)
        try:
            retained(self.before, after)
        except UpdateError:
            self.data_failed = True
            raise
        now = self.inspect()
        require(now["postgres"]["Id"] == self.rows["postgres"]["Id"] and now["postgres"]["Image"] == self.rows["postgres"]["Image"] and mounts(now["postgres"]) == self.pg_mounts, "PostgreSQL changed unexpectedly.")
        for name in ("api",):
            require(mounts(now[name]) == mounts(self.rows[name]), "Application storage changed unexpectedly.")
            for key, value in self.config["services"][name].get("environment", {}).items():
                require(environment(now[name]).get(key) == str(value), "Application settings changed unexpectedly.")
        result = json.loads(run(["docker", "exec", now["api"]["Id"], "wget", "-qO-", "http://127.0.0.1:8080/api/health"], label="Updated version check"))
        require(result.get("version") == version, "The updated API reports an unexpected version.")
        self.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "web")
        now = self.inspect()
        require(now["web"]["HostConfig"]["PortBindings"] == self.rows["web"]["HostConfig"]["PortBindings"] and mounts(now["web"]) == mounts(self.rows["web"]), "The web port or storage changed unexpectedly.")
        require((self.env_path.read_bytes() if self.env_path.exists() else None) == self.env_original, "Private environment settings changed unexpectedly.")
        (self.target / "VERSION").write_text(version + "\n")
        (self.target / "image-tag.txt").write_text(tag + "\n")
        private_json(self.backup / "update-passed.json", {"from": self.current, "to": version, "usersRetained": len(self.before["users"]), "requestsRetained": len(self.before["requests"])})
        print(f"\nUpdate passed: Reelio {version}. Original users, requests, integration settings, branding, storage and port retained.\nPrivate backup: {self.backup}\nCopy this entire private backup folder off the server. Never upload it to a public issue.")
        self.changed = self.paused = False

    def rollback(self):
        if not self.paused:
            if self.prepared:
                self.restore_image_references()
            return
        print("\nUpdate stopped. Recovering the previous application configuration and images...", file=sys.stderr)
        if self.changed:
            self.compose("stop", "--timeout", "30", "web", "api")
            for path, content in self.originals.items():
                path.write_bytes(content)
            for name, content in self.old_metadata.items():
                path = self.target / name
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(content)
            self.restore_image_references()
            self.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "api")
            if not self.data_failed:
                self.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180", "web")
        else:
            self.compose("start", "api", "web")
        print(f"Previous application selected. The database was NOT automatically restored. Backup: {self.backup}", file=sys.stderr)
        if self.data_failed:
            print("Data verification needs investigation. Web remains stopped; use the verified backup and recovery guide.", file=sys.stderr)

    def restore_image_references(self):
        for name in ("api", "web"):
            reference = self.config["services"][name]["image"]
            if not reference.startswith("sha256:") and "@sha256:" not in reference:
                run(["docker", "image", "tag", self.rows[name]["Image"], reference], label="Restoring the previous image selection")


def main():
    parser = argparse.ArgumentParser(description="Update an existing Reelio installation while retaining its data and setup.")
    parser.add_argument("--target")
    parser.add_argument("--check", action="store_true", help="Inspect compatibility without building images or stopping services")
    parser.add_argument("--bundle", type=Path, help="Use an already downloaded verified compiled bundle")
    args = parser.parse_args()
    require(sys.platform == "linux" and os.uname().machine == "x86_64" and os.geteuid() == 0, "Run this on the Linux amd64 Docker server with sudo or as root.")
    os.umask(0o077)
    run(["docker", "info"], label="Docker availability check")
    endpoint = run(["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], label="Docker context check").strip()
    if not os.environ.get("DOCKER_CONTEXT"):
        endpoint = os.environ.get("DOCKER_HOST", endpoint)
    require(endpoint.startswith("unix://"), "Remote Docker contexts are not supported. Run setup on the Docker host.")
    target = select_target(args.target)
    with ExitStack() as resources:
        lock = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        resources.callback(os.close, lock)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UpdateError("Another guided update is already using this directory.") from error
        installation = Installation(target)
        try:
            with tempfile.TemporaryDirectory(prefix="reelio-update-") as temporary:
                work = Path(temporary)
                if args.bundle:
                    bundle = args.bundle.resolve(strict=True)
                    selected = validate_bundle(bundle)
                    manifest = None
                else:
                    manifest = stable_release(work)
                    selected = manifest["version"]
                    bundle = None
                require(version_tuple(selected) >= version_tuple(installation.current), "Downgrades are refused. The existing application is newer than the selected stable release.")
                installation.summary(selected)
                if args.check:
                    installation.plan("preflight")
                    print("Compatibility checks passed. No images were built and no services or configuration were changed.")
                    return
                if selected == installation.current:
                    if os.environ.get("REELIO_NONINTERACTIVE") == "1":
                        if os.environ.get("REELIO_REAPPLY") != "1":
                            print("Already on this version. Nothing to update.")
                            return
                    elif ask("Already on this version. Reapply the same release?", "n").lower() not in ("y", "yes"):
                        print("Nothing was changed.")
                        return
                print(f"\nLicence: {REPOSITORY}/blob/main/LICENSE.txt\nThe updater will save a private full backup, briefly pause API/web, update their images and verify retained data.")
                if os.environ.get("REELIO_NONINTERACTIVE") == "1":
                    require(os.environ.get("REELIO_ACCEPT_LICENSE") == "1" and os.environ.get("REELIO_UPDATE_CONFIRM") == "1", "Unattended updates require REELIO_ACCEPT_LICENSE=1 and REELIO_UPDATE_CONFIRM=1.")
                else:
                    require(ask("Accept the licence and update this installation?", "n").lower() in ("y", "yes"), "Update cancelled. Nothing was changed.")
                if bundle is None:
                    print("Downloading and verifying the stable release directly on this server...")
                    bundle = release_bundle(manifest, work)
                tag = (bundle / "image-tag.txt").read_text().strip()
                installation.plan(tag)
                docker_root = Path(run(["docker", "info", "--format", "{{.DockerRootDir}}"], label="Docker storage check").strip())
                require(docker_root.is_dir() and shutil.disk_usage(docker_root).free >= 1024 * 1024 * 1024,
                        "Docker needs at least 1 GiB free before preparing update images.")
                print("Preparing the application images while the current app stays online...")
                installation.prepared = True
                run(["sh", str(bundle / "prepare-images.sh")], label="Preparing official application runtime images")
                installation.check_new_backup_permissions(tag)
                installation.verify_unchanged()
                storage = installation.backup_storage()
                installation.create_backup(storage)
                installation.apply(selected, tag)
        except BaseException:
            try:
                installation.rollback()
            except BaseException:
                print(f"Automatic application recovery also needs attention. Keep the database and backup intact: {installation.backup}", file=sys.stderr)
            raise
        finally:
            if installation.stage:
                installation.stage.unlink(missing_ok=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(InterruptedError("Update interrupted")))
    try:
        main()
    except (UpdateError, OSError, ValueError, KeyError, KeyboardInterrupt) as error:
        # Do not dump subprocess arguments, rendered config, URLs containing
        # database credentials, or a traceback to a shared terminal/log.
        print(f"\n{str(error) if isinstance(error, UpdateError) else 'Update could not finish; inspect the saved backup and server prerequisites.'}", file=sys.stderr)
        sys.exit(1)
