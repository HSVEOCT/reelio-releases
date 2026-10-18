# Updates and backups

Use a released bundle rather than pulling an unversioned `latest` image. A candidate is tested at home before its exact archive is promoted to a stable release.

## Back up

Run `sh backup.sh` inside the existing install directory. This briefly stops the API and web service, takes a PostgreSQL custom-format dump, checks that the dump is readable, copies the current Compose configuration and private `.env`, then starts the application again. The resulting private directory is printed and recorded in `.last-backup`.

Copy that directory off the server. Also preserve any files in the application's backups volume that you wish to retain. These directories contain secrets and personal data; never post them to GitHub.

## Update

Download and verify the new archive, extract it into a **different** directory, then run:

```sh
sh /path/to/new-bundle/update.sh /path/to/existing-install
```

The updater first backs up the existing installation, loads the new images, retains `.env` settings and named volumes, changes the versioned image tag and waits for healthy services. It does not delete volumes or update PostgreSQL to a new major version.

If startup fails, the previous image selection and configuration are restored. The database is not automatically rolled back, to avoid discarding new writes. Always read a release's migration notes before upgrading.

## Restore after a failed migration

Keep the existing volume until recovery has been checked. Stop API and web, restore the previous Compose file and `.env`, and start PostgreSQL only. Restore the saved dump into a fresh, isolated database using the same PostgreSQL major version, validate the data, then bring up the previous application images against that database. Do not run a destructive restore against your only copy.

The maintainer's current home instance is a separate deployment. These scripts do not migrate it automatically.
