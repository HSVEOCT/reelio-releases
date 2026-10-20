#!/usr/bin/env sh
set -eu
umask 077
bundle="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ "$#" -eq 1 ] || { echo 'Usage: sh NEW-BUNDLE/update.sh EXISTING-INSTALL-DIRECTORY' >&2; exit 1; }
target="$(CDPATH= cd -- "$1" && pwd)"
[ "$target" != / ] && [ "$target" != "$bundle" ]
[ -s "$target/.env" ] && [ -s "$target/backup.sh" ]
cd "$bundle"
sha256sum -c SHA256SUMS
sh "$target/backup.sh"
backup="$(cat "$target/.last-backup")"
# Retain the previous compiled payload as well as database/configuration.
[ ! -L "$target/web" ] && [ ! -L "$target/reelio-api" ] || { echo 'Application payload must not be symlinked.' >&2; exit 1; }
mkdir "$backup/payload"
payload='reelio-api web api.Dockerfile web.Dockerfile web.nginx.conf prepare-images.sh install.sh guided-update.py reelio-telemetry.py backup.sh update.sh INSTALL.md UPDATING.md LICENSE.txt THIRD_PARTY_NOTICES.txt build.json source-commit.txt postgres-image.txt SHA256SUMS'
for name in $payload; do
  if [ -e "$target/$name" ]; then cp -a "$target/$name" "$backup/payload/$name"; fi
done
sh ./prepare-images.sh
tag="$(cat image-tag.txt)"
case "$tag" in ''|*[!a-zA-Z0-9._-]*) exit 1;; esac
rollback() {
  status=$?
  if [ "$status" -ne 0 ]; then
    if [ -d "$backup/payload/web" ]; then
      if [ -d "$target/web" ]; then mv "$target/web" "$backup/failed-web"; fi
      cp -a "$backup/payload/web" "$target/web"
    fi
    for name in $payload; do
      [ "$name" != web ] || continue
      if [ -f "$backup/payload/$name" ]; then cp -a "$backup/payload/$name" "$target/$name"; fi
    done
    cp "$backup/.env" "$backup/docker-compose.yml" "$backup/VERSION" "$backup/image-tag.txt" "$target/"
    (cd "$target" && docker compose --env-file .env up -d --pull never --wait --wait-timeout 180) || true
    echo "Update failed. Previous images selected; backup retained at $backup. Database was not automatically rolled back." >&2
  fi
}
trap rollback EXIT
cp docker-compose.yml VERSION image-tag.txt "$target/"
sed -i "s/^REELIO_IMAGE_TAG=.*/REELIO_IMAGE_TAG=$tag/" "$target/.env"
cd "$target"
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --pull never --wait --wait-timeout 180
# Refresh the on-disk compiled application too; retain private .env and volumes.
if [ -d "$target/web" ]; then mv "$target/web" "$backup/previous-web"; fi
cp -a "$bundle/web" "$target/web"
for name in $payload; do
  [ "$name" != web ] || continue
  if [ -f "$bundle/$name" ]; then cp -a "$bundle/$name" "$target/$name"; fi
done
trap - EXIT
echo "Update complete. Backup: $backup"
