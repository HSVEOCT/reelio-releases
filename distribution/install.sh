#!/usr/bin/env sh
set -eu
umask 077
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v docker >/dev/null
command -v openssl >/dev/null || { echo 'Install openssl first.' >&2; exit 1; }
docker compose version >/dev/null
[ ! -e .env ] || { echo '.env already exists. Use the update guide for an existing installation.' >&2; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo 'This bundle supports Linux amd64 only.' >&2; exit 1; }
sha256sum -c SHA256SUMS
project="${REELIO_PROJECT:-reelio-public}"
case "$project" in ''|*[!a-z0-9_-]*) echo 'Invalid REELIO_PROJECT' >&2; exit 1;; esac
case "$project" in [a-z0-9]*) ;; *) echo 'Project name must start with a lowercase letter or digit' >&2; exit 1;; esac
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$project")" ] || [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$project")" ]; then
  echo "Compose project $project already exists. Use its existing installation, or choose a different REELIO_PROJECT." >&2
  exit 1
fi
port="${REELIO_PORT:-43834}"
case "$port" in ''|*[!0-9]*) echo 'Invalid REELIO_PORT' >&2; exit 1;; esac
[ "$port" -ge 1024 ] && [ "$port" -le 65535 ]
if command -v ss >/dev/null 2>&1 && ss -H -ltn "sport = :$port" | grep -q .; then
  echo "Port $port is in use. Set REELIO_PORT to an unused port and retry." >&2
  exit 1
fi
password="$(openssl rand -hex 32)"
tag="$(cat image-tag.txt)"
case "$tag" in ''|*[!a-zA-Z0-9._-]*) echo 'Invalid image tag' >&2; exit 1;; esac
cp .env.example .env
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$password/;s/^REELIO_IMAGE_TAG=.*/REELIO_IMAGE_TAG=$tag/;s/^REELIO_PORT=.*/REELIO_PORT=$port/;s/^REELIO_PROJECT=.*/REELIO_PROJECT=$project/" .env
chmod 600 .env
sh ./prepare-images.sh
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --pull never --wait --wait-timeout 180
echo "Reelio is ready at http://127.0.0.1:$port"
echo 'For a remote server, use an SSH tunnel as described in INSTALL.md.'
echo 'Create the owner account, then configure your own integrations.'
