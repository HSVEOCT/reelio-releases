#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = x86_64 ] || {
  echo 'This bundle supports Linux amd64 only.' >&2
  exit 1
}
tag="$(cat image-tag.txt)"
case "$tag" in ''|*[!a-zA-Z0-9._-]*) exit 1;; esac
version="$(cat VERSION)"
revision="$(cat source-commit.txt)"
case "$revision" in ''|*[!a-f0-9]*) exit 1;; esac
echo 'Preparing Reelio images from the compiled app and official runtime images...'
docker build --platform linux/amd64 --pull --label "org.opencontainers.image.version=$version" --label "org.opencontainers.image.revision=$revision" -f api.Dockerfile -t "reelio/api:$tag" .
docker build --platform linux/amd64 --pull --label "org.opencontainers.image.version=$version" --label "org.opencontainers.image.revision=$revision" -f web.Dockerfile -t "reelio/web:$tag" .
postgres="$(cat postgres-image.txt)"
case "$postgres" in postgres@sha256:*|docker.io/library/postgres@sha256:*) ;; *) echo 'Unexpected PostgreSQL image reference.' >&2; exit 1;; esac
[ -n "$postgres" ] || { echo 'Pinned PostgreSQL image missing.' >&2; exit 1; }
docker pull --platform linux/amd64 "$postgres"
