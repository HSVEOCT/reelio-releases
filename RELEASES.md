# Release channels and checks

1. The separate private source repository builds the API and browser assets and runs API/frontend checks.
2. The candidate bundle contains compiled application files, public runtime Dockerfiles, installation/update/backup scripts, licences, dependency notices, checksums and a build manifest.
3. It contains no saved Linux container images, application source checkout, live configuration, database, API credentials or AI worker. Official runtime images are pinned by digest and fetched directly during local assembly. Runtime packages come from Alpine's repositories.
4. Automated checks use the shipped installer, create an owner, log in, check the version and legal files, save branding, validate a backup and run the updater with isolated Docker volumes.
5. The maintainer tests the exact candidate archive at home, including its installation/update path and recovery. Results from a previous packaging format do not establish that a new format has been tested.
6. A deliberate promotion records the candidate run, source commit, archive digest, home-test confirmation and licensing review. It publishes the tested archive without rebuilding it.

Preview releases are marked as prereleases. A stable release is an explicit promotion, never an automatic deployment of each source change. Installing an update is the user's choice; Reelio does not silently replace a running installation.

## Current status

[Reelio 1.0.18 is the current stable release](https://github.com/HSVEOCT/reelio-releases/releases/tag/v1.0.18). Its exact home-tested archive is available with a SHA256 checksum. Optional support is available through [Ko-fi](https://ko-fi.com/reelio).

Archive SHA256: `038daa8e063031878e52beb3c49baac58cb48f2bdd4a4a8c039397fbf2e33e85`.

## What to keep

Retain the official bundle, checksum, notices and release notes alongside your private backups. The compiled-application bundle requires internet access to assemble runtime images. It is not an offline image export. See [updates and recovery](UPDATING.md).
