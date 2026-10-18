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
gzip -dc images.tar.gz | docker load
tag="$(cat image-tag.txt)"
case "$tag" in ''|*[!a-zA-Z0-9._-]*) exit 1;; esac
rollback() {
  status=$?
  if [ "$status" -ne 0 ]; then
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
cp "$bundle/backup.sh" "$bundle/update.sh" "$target/"
trap - EXIT
echo "Update complete. Backup: $backup"
