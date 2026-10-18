#!/usr/bin/env sh
set -eu
umask 077
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
[ -s .env ]
backup="$(mktemp -d "${PWD}/backup-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
compose() { docker compose --env-file .env "$@"; }
resume() { compose start api web >/dev/null 2>&1 || true; }
trap resume EXIT
compose stop web api
compose exec -T postgres pg_dump -U reelio -d reelio -Fc > "$backup/database.dump"
compose exec -T postgres pg_restore --file=/dev/null < "$backup/database.dump"
cp .env docker-compose.yml VERSION image-tag.txt "$backup/"
compose images -q > "$backup/image-ids.txt"
printf '%s\n' "$backup" > .last-backup
echo "Verified database and configuration backup: $backup"
echo 'Copy this private directory off the server. Preserve the backups volume separately.'
