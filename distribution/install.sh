#!/usr/bin/env sh
# Reelio guided installer. Application source is not included.
set -eu
umask 077

fail() { printf '\n%s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
interactive=true
[ "${REELIO_NONINTERACTIVE:-0}" != 1 ] || interactive=false
if "$interactive"; then
  { exec 3<>/dev/tty; } 2>/dev/null || fail 'Run this script in a terminal, for example: sudo sh ./reelio-install.sh'
fi
ask() {
  question=$1; answer=$2
  if "$interactive"; then
    printf '%s [%s]: ' "$question" "$answer" >&3
    IFS= read -r reply <&3 || fail 'Setup cancelled: terminal closed.'
    [ -z "$reply" ] || answer=$reply
  fi
}
yes() { ask "$1" "$2"; case "$answer" in y|Y|yes|YES) return 0;; *) return 1;; esac; }
fetch() { curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 20 --max-time 600 --retry 2 "$1" -o "$2"; }
value() { sed -n "s/^$1=//p" "$target/.env"; }
ready() {
  public=$(value PUBLIC_URL); bind=$(value REELIO_BIND); saved_port=$(value REELIO_PORT)
  say ''
  say 'Reelio is running and its health checks passed.'
  if [ -n "$public" ]; then
    say "Open: $public"
    say "Your existing HTTPS proxy must forward that hostname to http://$bind:$saved_port."
    say 'The installer does not create DNS records or configure your reverse proxy.'
  else
    say "Open: http://$bind:$saved_port"
  fi
  say 'Create your owner account, then open Admin > Integrations to add your own TMDB and media services.'
  say "Settings and application files: $target"
  say "Back up later: cd '$target' && sudo sh backup.sh"
}
start() {
  cd "$target"
  docker compose --env-file .env config --quiet
  sh ./prepare-images.sh
  docker compose --env-file .env up -d --pull never --wait --wait-timeout 180
  rm -f .reelio-setup-pending
  ready
}

[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || fail 'Reelio currently requires a Linux amd64/x86_64 server. Run this on that server, not on your Windows PC or Mac.'
[ "$(id -u)" = 0 ] || fail 'Run with sudo, or as root in your server console: sudo sh ./reelio-install.sh'
self=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)/$(basename -- "$0")
scratch=''
target=''
cleanup() {
  status=$?
  if [ "$status" -ne 0 ] && [ -n "$target" ] && [ -f "$target/.reelio-setup-pending" ]; then
    printf '\nSetup stopped. Your files and database have been kept.\nRetry: sudo sh "%s/setup.sh" --resume "%s"\n' "$target" "$target" >&2
  fi
  if [ -n "$scratch" ]; then
    case "$scratch" in /tmp/reelio-setup.*) rm -rf -- "$scratch";; esac
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [ "$#" -gt 0 ]; then
  [ "$#" -eq 2 ] && [ "$1" = --resume ] || fail 'Usage: sh install.sh [--resume INSTALL-DIRECTORY]'
  target=$(CDPATH='' cd -- "$2" && pwd)
  [ -f "$target/.env" ] && [ -f "$target/.reelio-setup-pending" ] && [ "$(cat "$target/.reelio-setup-pending")" = reelio-setup-v1 ] || fail 'This directory is not an interrupted guided installation. Existing installations must use the update guide.'
  command -v docker >/dev/null && docker info >/dev/null 2>&1 && docker compose version >/dev/null || fail 'Docker Engine and Compose v2 must be running before resuming.'
  endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
  if [ -z "${DOCKER_CONTEXT:-}" ]; then endpoint=${DOCKER_HOST:-$endpoint}; fi
  case "$endpoint" in unix://*) ;; *) fail 'Use a local Docker Engine; remote Docker contexts are not supported by this setup wizard.';; esac
  say "Resuming the saved configuration in $target."
  start
  exit 0
fi

say ''
say 'Welcome to Reelio'
say 'This wizard installs a fresh copy on this Linux server.'
say 'Existing Reelio installations must use the update guide.'
if command -v systemd-detect-virt >/dev/null 2>&1 && [ "$(systemd-detect-virt 2>/dev/null || true)" = lxc ]; then
  say 'LXC detected. Docker must be permitted by your Proxmox/LXC configuration; this script does not change the host.'
fi
say ''
ask 'Installation folder (use an empty, dedicated folder)' "${REELIO_INSTALL_DIR:-/opt/reelio}"
target=$answer
case "$target" in /*) ;; *) fail 'Choose an absolute installation path, such as /opt/reelio.';; esac
case "$target" in *[!a-zA-Z0-9_./-]*|*/../*|*/..|*/./*|*/.|*//*|*/) fail 'Use a simple absolute folder path without spaces, trailing slashes, or . / .. path segments.';; esac
case "$target" in /|/opt|/srv|/var|/home|/root|/usr|/tmp|/etc|/var/lib) fail 'Choose a dedicated subfolder, such as /opt/reelio.';; esac
if [ -e "$target" ] || [ -L "$target" ]; then
  [ -d "$target" ] && [ ! -L "$target" ] && [ -z "$(ls -A "$target")" ] || fail "The folder $target already contains files or is a symlink. Nothing was changed. Choose a new folder; use the update guide for an existing install."
fi
ask 'Compose project name (unique for this installation)' "${REELIO_PROJECT:-reelio-public}"
project=$answer
case "$project" in ''|*[!a-z0-9_-]*) fail 'Use lowercase letters, digits, hyphens or underscores for the project.';; esac
case "$project" in [a-z0-9]*) ;; *) fail 'The project must start with a lowercase letter or digit.';; esac

say ''
say 'How will you open Reelio?'
say '  1) Home network / LAN (recommended for a homelab)'
say '  2) Through an existing HTTPS reverse proxy and domain'
say '  3) Only on this server (localhost)'
ask 'Choose 1, 2 or 3' "${REELIO_ACCESS:-1}"
access=$answer
case "$access" in 1|2|3) ;; *) fail 'Choose 1, 2 or 3.';; esac
detected=''
if command -v ip >/dev/null 2>&1; then
  detected=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<NF;i++) if($i=="src") {print $(i+1); exit}}')
fi
if [ -z "$detected" ] && command -v hostname >/dev/null 2>&1; then detected=$(hostname -I 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i ~ /^[0-9.]+$/) {print $i; exit}}'); fi
bind=127.0.0.1; public=''; secure=false; trust=false
case "$access" in
  1) ask 'Server LAN IPv4 address (check its network settings if blank)' "${REELIO_BIND:-$detected}"; bind=$answer;;
  2)
    ask 'Your existing HTTPS address (for example https://reelio.example.com)' "${PUBLIC_URL:-}"
    public=${answer%/}
    case "$public" in *[!a-zA-Z0-9.:/-]*) fail 'Enter one HTTPS hostname without whitespace or extra settings.';; esac
    printf '%s\n' "$public" | grep -Eq '^https://[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?(:[0-9]{1,5})?$' || fail 'Enter an HTTPS hostname, optionally with a port, without paths, credentials or query strings.'
    hostname_port=${public#https://}
    case "$hostname_port" in *:*) url_port=${hostname_port##*:}; [ "$url_port" -ge 1 ] && [ "$url_port" -le 65535 ] || fail 'The HTTPS address contains an invalid port.';; esac
    secure=true
    say 'The proxy forwards to Reelio over HTTP. DNS, certificates and proxy configuration must already be managed by you.'
    say 'For a proxy on this server, choose 127.0.0.1. For another machine/container, choose a reachable IPv4 address on this server.'
    ask 'IPv4 address Reelio should listen on' "${REELIO_BIND:-127.0.0.1}"; bind=$answer
    # Forwarded headers stay untrusted unless the operator explicitly opts in.
    if yes 'Will ONLY your trusted proxy be able to reach this backend? Trust its forwarded headers?' "${TRUST_PROXY:-n}"; then trust=true; fi
    ;;
  3) bind=127.0.0.1;;
esac
printf '%s\n' "$bind" | awk -F. 'NF!=4 {exit 1} {for(i=1;i<=4;i++) if($i !~ /^[0-9]+$/ || length($i)>3 || $i>255 || (length($i)>1 && substr($i,1,1)=="0")) exit 1}' || fail 'Enter a valid IPv4 address belonging to this server.'
[ "$bind" != 0.0.0.0 ] || fail 'Choose one server IPv4 address rather than exposing Reelio on every interface.'
if [ "$access" = 1 ]; then
  case "$bind" in 127.*) fail 'For LAN access, choose the LAN address of this server, not localhost.';; esac
fi
ask 'Host port (saved for future restarts and updates)' "${REELIO_PORT:-43834}"
port=$answer
case "$port" in ''|*[!0-9]*|0*) fail 'Enter a port number without leading zeros.';; esac
[ "${#port}" -le 5 ] && [ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || fail 'Choose a port from 1024 to 65535.'

say ''
say "Folder: $target"
say "Project: $project"
say "Listen on: http://$bind:$port"
[ -z "$public" ] || say "Browser address: $public (through your HTTPS proxy)"
say 'Licence: free personal, non-commercial use. Read https://github.com/HSVEOCT/reelio-releases/blob/main/LICENSE.txt'
if "$interactive"; then
  yes 'Do you accept the Reelio Personal Use Licence and want to continue?' n || fail 'Setup cancelled. No installation was started.'
else
  [ "${REELIO_ACCEPT_LICENSE:-0}" = 1 ] || fail 'Unattended setup requires REELIO_ACCEPT_LICENSE=1 after reviewing the licence.'
fi

missing=false
for tool in curl openssl tar gzip sha256sum ss ip; do command -v "$tool" >/dev/null 2>&1 || missing=true; done
if "$missing"; then
  command -v apt-get >/dev/null 2>&1 || fail 'Install curl, ca-certificates, openssl, tar, gzip, coreutils and iproute2, then rerun.'
  "$interactive" || fail 'Install curl, ca-certificates, openssl, tar, gzip, coreutils and iproute2 before unattended setup.'
  yes 'Install the missing setup tools using apt?' y || fail 'Setup tools are required to continue.'
  apt-get update
  apt-get install -y ca-certificates curl openssl tar gzip coreutils iproute2
fi
scratch=$(mktemp -d /tmp/reelio-setup.XXXXXXXX)
if ! command -v docker >/dev/null 2>&1; then
  [ -r /etc/os-release ] || fail 'Install Docker Engine and Compose v2 for your Linux distribution, then rerun.'
  . /etc/os-release
  case "${ID:-}" in ubuntu|debian) ;; *) fail 'Automatic Docker installation supports Ubuntu and Debian. Install Docker Engine and Compose v2 for your distribution, then rerun.';; esac
  # Never remove, replace or upgrade somebody else's container runtime.
  for package in docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc; do
    if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      fail "An existing container runtime package ($package) was found. Set up Docker Engine and Compose v2 yourself; Reelio will not replace it."
    fi
  done
  "$interactive" || fail 'Install Docker Engine and Compose v2 before unattended setup.'
  yes "Docker is missing. Install Docker Engine and Compose from Docker's official $ID apt repository?" y || fail 'Docker is required to continue.'
  codename=${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}
  case "$codename" in ''|*[!a-zA-Z0-9_-]*) fail 'Cannot detect a supported distribution codename.';; esac
  [ ! -e /etc/apt/sources.list.d/docker.sources ] && [ ! -e /etc/apt/sources.list.d/docker.list ] && [ ! -e /etc/apt/keyrings/docker.asc ] || fail 'Docker repository settings already exist. Complete your Docker installation first; Reelio will not overwrite them.'
  fetch "https://download.docker.com/linux/$ID/dists/$codename/Release" "$scratch/docker-release"
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  fetch "https://download.docker.com/linux/$ID/gpg" "$scratch/docker.asc"
  install -m 0644 "$scratch/docker.asc" /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/$ID
Suites: $codename
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi
docker info >/dev/null 2>&1 || fail 'Docker is installed but is not available. Start Docker first. In Proxmox LXC, check the Docker/nesting configuration of your container.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is missing. Install it for your existing Docker installation, then rerun. See https://docs.docker.com/compose/install/linux/'
endpoint=$(docker context inspect --format '{{.Endpoints.docker.Host}}')
if [ -z "${DOCKER_CONTEXT:-}" ]; then endpoint=${DOCKER_HOST:-$endpoint}; fi
case "$endpoint" in unix://*) ;; *) fail 'Use a local Docker Engine; remote Docker contexts are not supported by this setup wizard.';; esac
ip -4 -o address show | awk -v wanted="$bind" '{split($4,a,"/"); if(a[1]==wanted) found=1} END {exit !found}' || fail "The address $bind is not assigned to this server. Rerun and choose one of its IPv4 addresses."
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$project")" ] || [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$project")" ] || [ -n "$(docker network ls -q --filter "label=com.docker.compose.project=$project")" ]; then
  fail "Compose project $project is already in use. Choose a different project; existing data was left alone."
fi
published_ports=$(docker ps --format '{{.Ports}}')
if [ -n "$(ss -H -ltn "sport = :$port")" ] || printf '%s\n' "$published_ports" | grep -Eq "(^|[ ,])[^ ,]*:$port->"; then
  fail "Port $port is already in use. Rerun and choose another port; existing applications were left alone."
fi
parent=$target
while [ ! -d "$parent" ]; do parent=$(dirname -- "$parent"); done
[ "$(df -Pk "$parent" | awk 'END {print $4}')" -ge 1048576 ] || fail 'At least 1 GiB of free disk space is required for setup; allow more for images, database and backups.'
docker_root=$(docker info --format '{{.DockerRootDir}}')
[ -d "$docker_root" ] && [ "$(df -Pk "$docker_root" | awk 'END {print $4}')" -ge 1048576 ] || fail 'Docker needs at least 1 GiB of free storage; allow more as your data grows.'

# The same wizard can run from a future release bundle or download today's
# published compiled-application bundle without changing that archive's bytes.
bundle=$(dirname -- "$self")
if [ ! -f "$bundle/SHA256SUMS" ]; then
  say 'Finding the current stable Reelio release...'
  fetch https://raw.githubusercontent.com/HSVEOCT/reelio-releases/main/site/release.json "$scratch/release.json"
  version=$(sed -n 's/^[[:space:]]*"version":[[:space:]]*"\([0-9][0-9.]*\)",*[[:space:]]*$/\1/p' "$scratch/release.json")
  case "$version" in ''|*[!0-9.]*) fail 'The stable release manifest must contain one valid version.';; esac
  printf '%s\n' "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || fail 'The stable release manifest does not contain one valid version.'
  expected=$(sed -n 's/^[[:space:]]*"sha256":[[:space:]]*"\([a-f0-9]*\)",*[[:space:]]*$/\1/p' "$scratch/release.json")
  [ "${#expected}" -eq 64 ] || fail 'The stable release manifest has no valid archive checksum.'
  archive="reelio-$version-linux-amd64.tar.gz"
  url="https://github.com/HSVEOCT/reelio-releases/releases/download/v$version/$archive"
  say "Downloading Reelio $version directly to this server..."
  fetch "$url" "$scratch/$archive"
  fetch "$url.sha256" "$scratch/$archive.sha256"
  actual=$(sha256sum "$scratch/$archive" | awk '{print $1}')
  [ "$actual" = "$expected" ] || fail 'The download does not match the stable release checksum. Nothing was installed.'
  awk -v hash="$expected" -v name="$archive" 'NR==1 && NF==2 && $1==hash && $2==name {ok=1;next} {ok=0;exit 1} END {if(NR!=1 || !ok) exit 1}' "$scratch/$archive.sha256" || fail 'The release checksum file does not match the downloaded archive.'
  tar -tzf "$scratch/$archive" > "$scratch/paths"
  awk '/^\// || /(^|\/)\.\.(\/|$)/ || /[^a-zA-Z0-9_.\/-]/ {exit 1}' "$scratch/paths" || fail 'The archive contains an unexpected path.'
  tar -tvzf "$scratch/$archive" | awk 'substr($0,1,1)!="-" && substr($0,1,1)!="d" {exit 1}' || fail 'The archive contains links or special files.'
  mkdir "$scratch/bundle"
  tar -xzf "$scratch/$archive" --no-same-owner --no-same-permissions -C "$scratch/bundle"
  bundle=$scratch/bundle
  [ "$(cat "$bundle/VERSION")" = "$version" ] || fail 'The downloaded application version does not match the release manifest.'
fi
for file in SHA256SUMS build.json VERSION image-tag.txt .env.example docker-compose.yml prepare-images.sh backup.sh update.sh LICENSE.txt; do
  [ -s "$bundle/$file" ] || fail "The application bundle is missing $file."
done
grep -Eq '"packaging"[[:space:]]*:[[:space:]]*"compiled-application"' "$bundle/build.json" || fail 'This installer requires a compiled-application release bundle (1.0.17 or newer).'
(cd "$bundle" && sha256sum -c SHA256SUMS) || fail 'Application file verification failed. Nothing was installed.'
tag=$(cat "$bundle/image-tag.txt")
case "$tag" in ''|*[!a-zA-Z0-9._-]*) fail 'Invalid application image tag.';; esac
say "Installing Reelio $(cat "$bundle/VERSION")..."
# Reserve the destination atomically; never copy over an existing directory.
if [ -d "$target" ]; then rmdir -- "$target" || fail 'The destination is no longer empty.'; fi
mkdir -p -- "$(dirname -- "$target")"
mkdir -- "$target" || fail 'Cannot reserve the installation folder. Nothing was overwritten.'
cp -R "$bundle/." "$target/"
cp "$self" "$target/setup.sh"
password=$(openssl rand -hex 32)
cat > "$target/.env" <<EOF
# Private Reelio settings. Do not attach this file to a public issue.
REELIO_PROJECT=$project
REELIO_BIND=$bind
REELIO_PORT=$port
REELIO_IMAGE_TAG=$tag
POSTGRES_PASSWORD=$password
PUBLIC_URL=$public
SECURE_COOKIE=$secure
TRUST_PROXY=$trust
DISPATCH_CONCURRENCY=4
EOF
chmod 600 "$target/.env"
printf '%s\n' reelio-setup-v1 > "$target/.reelio-setup-pending"
say 'Preparing runtime images and starting Reelio. The first run can take a few minutes...'
start
