# Updates, backups and recovery

Use a versioned official bundle and read its release notes. There is no unattended `latest` update. Your private `.env`, project name, port and named volumes are retained.

## Back up

Inside the existing install directory, run:

```sh
sh backup.sh
```

This briefly stops API and web, takes a PostgreSQL custom-format dump, checks that it is readable, copies the current Compose file, private `.env`, version and image tag, then starts the app again. The backup directory is printed and recorded in `.last-backup`.

Copy that private directory off the server. Preserve any files in the application's backups volume separately if you need them. Never attach these files to a public issue. A readable dump is not proof of full recovery; rehearse restoring it into an isolated database.

## Update an existing public-bundle installation

Download the new archive and checksum from [Releases](https://github.com/HSVEOCT/reelio-releases/releases), verify it and extract it into a **different** directory. Run:

```sh
sh /path/to/new-bundle/update.sh /path/to/existing-install
```

The updater verifies the bundle, backs up the existing install, assembles the new runtime images using official upstream downloads, changes the versioned application images and waits for healthy services. Network access and free disk space are required; Go/Node compilers and application source are not.

The updater supports installations made from the earlier private 1.0.15/1.0.16 public-bundle candidates. It does **not** automatically convert older custom migration layouts. PostgreSQL remains on major version 18; a release can select a newer PostgreSQL 18 runtime image. Major-version migrations need separate instructions.

Afterwards, check `docker compose --env-file .env ps`, sign in and confirm the version, history and integrations. Refresh cached browser assets if necessary. Keep the recovery backup and old images until checking is complete.

If startup fails, the updater restores the previous image selection, Compose configuration and `.env`. It does not automatically roll back the database, which could discard new writes. Recovery backups remain available. Health checks do not replace checking your own integrations.

## Rehearse recovery safely

Use an isolated Docker host or a separate Compose project and port. Block outbound integrations during recovery: a restored database can contain live credentials and queued jobs.

1. Keep the original installation and volumes intact. Copy the backup into a private recovery workspace.
2. Recover the **previous app version**, its image tag and compatible runtime images. Keep the official bundle and checksum alongside the off-server backup; a dump alone is not an app package.
3. Create a separate project with a unique name, fresh database volume, unused loopback-bound port and a new database password. Never reuse the live project name or volumes.
4. Start **PostgreSQL only**. Restore the dump into its fresh, empty Reelio database using `pg_restore --no-owner --no-acl --exit-on-error` with the recovery database credentials. Keep API and web stopped.
5. Check expected users, request counts and important settings directly in the recovered database. Verify the full restore, not just the dump's table of contents.
6. After blocking outbound access, start the previous API and web against this recovered database. Check login, requests and settings without dispatching restored jobs against live automation.
7. Plan any production switch separately and retain the original volume and backup until recovery has been checked.

For a production recovery, stop API and web, retain the current database for investigation, and restore into a separate database/volume. Select a compatible app version and check the recovered installation before directing users to it. Do not destructively restore over your only database copy.

Keep the dump, private configuration, any needed backup-volume files, previous official bundle/checksum/image tag, PostgreSQL major version and recovery test record together.

Never use `docker compose down -v` as an update or recovery step for the live installation.
