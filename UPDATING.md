# Update Reelio and keep your data

Use the same guided script as installation. Run these commands in the **Linux server's terminal**:

```sh
curl -fsSL https://raw.githubusercontent.com/HSVEOCT/reelio-releases/main/install.sh -o reelio-install.sh
sudo sh ./reelio-install.sh
```

Choose **2 — Update an existing installation**. If more than one copy is found, choose its folder. Check the detected project, current version, selected stable version and existing web address before accepting the update.

Already logged in as root? Omit `sudo`.

## Check first without updating

You can inspect a particular installation without stopping its services or building images:

```sh
sudo sh ./reelio-install.sh --check /path/to/reelio
```

To start its guided update directly:

```sh
sudo sh ./reelio-install.sh --update /path/to/reelio
```

Replace the path with the existing installation folder. The wizard detects its Compose project and files from the running containers. It does not create a replacement database or ask you to re-enter your integration credentials.

## What an update does

1. Checks that the existing API, web and PostgreSQL services are healthy, their saved configuration matches the running setup, and the database uses PostgreSQL 18.
2. Downloads and verifies the stable compiled application bundle. Prepares its runtime images while the current app stays online.
3. Saves the previous images and application/configuration files in a **private backup folder outside the installation directory**.
4. Briefly stops API and web. PostgreSQL stays running. Takes a custom-format database dump, reads the whole archive to verify it, and backs up the other data mounts and project volumes.
5. Changes the API/web image selections. Keeps the PostgreSQL container/image, database volume, other mounts, private `.env`, project, port, proxy settings and disabled workers.
6. Checks the expected version and original users, request IDs, integration settings and branding before reopening the web app. Prints the backup location.

If the selected version is already installed, you can leave it alone or explicitly reapply it. Downgrades and database major-version upgrades are refused.

## Supported existing layouts

- A public Reelio installation using one Compose file.
- A captured home migration layout using a base Compose file and a **JSON-format migration override**, including files named `docker-compose.override.yml`.

For a one-file layout, the updater writes the resolved configuration back as private JSON; Docker Compose accepts JSON in a `.yml` file. Literal dollar signs in settings are preserved. The `.env` file is kept byte-for-byte.

For the migration layout, the base file is untouched. Only the API/web image and pull-policy fields in the existing JSON override change. Source build paths are retained but not used to build the new app.

Custom YAML overrides, external or bind-mounted databases, replicas, running optional workers and inconsistent saved/running settings need separate review. The wizard refuses them before deployment rather than guessing how to migrate them. Stop an optional worker before updating; its retained data is backed up. This does not install or enable an AI worker.

## After the update

Sign in at your usual address and check the version, request history and integrations. Your existing browser session should remain valid. Keep the backup and previous images until you have checked your own services.

Copy the **whole private backup folder off the server**. It includes credentials and may include local application files; never attach it to a public issue. Allow space for the database, application files, previous Docker images and persistent data backups. Backups are retained until you remove them yourself.

The backup contains `application.tar.gz`, `images.tar.gz`, `database.dump`, `storage-*.tar.gz`, private configuration/container snapshots and a `verified.json` checksum record. A successful update adds `update-passed.json`.

## If an update fails

The updater attempts to recover the previous application configuration and image selections. It does **not** automatically restore the database, because that could discard new writes. The verified backup stays available.

If a data-retention check fails, the previous application images are selected and the web service remains stopped for investigation. If recovery cannot complete, the wizard says so and prints the backup location. Keep the existing database and all backups intact.

Rehearse a database recovery in a **separate project with fresh volumes** before making a production switch. Load the retained images, use the saved configuration and PostgreSQL version, restore `database.dump` with `pg_restore --no-owner --no-acl --exit-on-error`, and restore any needed storage archives using `storage.json` as the mount mapping. Block outbound integrations in a recovery copy so restored jobs cannot affect live services. Do not restore over your only live database.

Never use `docker compose down -v` on a live installation.

## Routine public-install backups

For an installation made from the public bundle, the existing backup helper is still available:

```sh
cd /path/to/reelio
sudo sh backup.sh
```

It briefly pauses API/web and creates a verified database/configuration backup. The guided updater's backup is more complete: it also retains the previous images and persistent mount contents.

Manual, versioned bundle downloads remain available in [Releases](https://github.com/HSVEOCT/reelio-releases/releases). Older bundled `update.sh` helpers are for their documented public layouts; use the current guided script for the supported home migration layout.
