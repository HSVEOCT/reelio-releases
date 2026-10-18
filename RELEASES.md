# Release channels and checks

1. The separate private source repository builds the API and browser assets and runs API/frontend checks.
2. The candidate bundle contains compiled application files, public runtime Dockerfiles, installation/update/backup scripts, licences, dependency notices, checksums and a build manifest.
3. It contains no saved Linux container images, application source checkout, live configuration, database, API credentials or AI worker. Official runtime images are pinned by digest and fetched directly during local assembly. Runtime packages come from Alpine's repositories.
4. Automated checks use the shipped installer, create an owner, log in, check the version and legal files, save branding, validate a backup and run the updater with isolated Docker volumes.
5. The maintainer tests the exact candidate archive at home, including its installation/update path and recovery. Results from a previous packaging format do not establish that a new format has been tested.
6. A deliberate promotion records the candidate run, source commit, archive digest, home-test confirmation and licensing review. It publishes the tested archive without rebuilding it.

Preview releases are marked as prereleases. A stable release is an explicit promotion, never an automatic deployment of each source change. Installing an update is the user's choice; Reelio does not silently replace a running installation.

## Current status

The first public download is being prepared. There is no published stable release yet. The website therefore keeps its preparation status instead of showing a download link. Donations are not configured.

## What to keep

Retain the official bundle, checksum, notices and release notes alongside your private backups. The compiled-application bundle requires internet access to assemble runtime images. It is not an offline image export. See [updates and recovery](UPDATING.md).
