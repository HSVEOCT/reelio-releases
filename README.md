# Reelio

A home for your family's next film night. Discover movies and shows, request missing titles and follow them into your Jellyfin library.

**Public distribution is being prepared. No stable download has been published yet.**

Reelio is free for personal, non-commercial self-hosting under the [Reelio Personal Use Licence](LICENSE.txt). The application source is private. This repository contains the public website, documentation and installation helpers; releases will contain compiled Docker images, not application source.

- [Get started](INSTALL.md)
- [Updates and backups](UPDATING.md)
- [How releases are tested](RELEASES.md)
- [Privacy and integrations](PRIVACY.md)
- [Report a problem](https://github.com/HSVEOCT/reelio-releases/issues)

Requires a Linux amd64 Docker host with Docker Compose v2. The first release targets Jellyfin, with optional Radarr and Sonarr integrations. No films, TV files, accounts, metadata credentials or download-service subscriptions are included.

There is no donation account configured yet. Donations will be entirely optional and will not unlock features. Third-party metadata permissions must be confirmed separately; a donation model is not assumed to waive provider terms.

## Repository boundaries

Application code and build workflows live in a separate private repository. Public files are copied through an explicit allowlist. The maintainer's home deployment has its own configuration, database and volumes and is never exposed by this website.

The first download will appear on the [Releases page](https://github.com/HSVEOCT/reelio-releases/releases) after build checks and home testing. GitHub's automatically generated source archives of **this** repository contain public distribution materials only, not the Reelio application.
