# Reelio

A home for your family's next film night. Discover movies and shows, request missing titles and follow them into your Jellyfin library.

**[Visit the Reelio website](https://hsveoct.github.io/reelio-releases/)**

**[Reelio 1.0.17 is available to download](https://github.com/HSVEOCT/reelio-releases/releases/tag/v1.0.17).**

Reelio is free for personal, non-commercial self-hosting under the [Reelio Personal Use Licence](LICENSE.txt). The application source is private. This repository contains the public website, documentation and installation helpers; release bundles contain the compiled API, browser assets and runtime assembly files. Application source is not included.

- [Get started](INSTALL.md)
- [Updates and backups](UPDATING.md)
- [How releases are tested](RELEASES.md)
- [Privacy and integrations](PRIVACY.md)
- [Licences and third-party components](THIRD-PARTY.md)
- [Report a problem](https://github.com/HSVEOCT/reelio-releases/issues)

Requires a Linux amd64 Docker host with Docker Compose v2 and internet access during installation or an update. Docker obtains official runtime components directly from their upstream distributors. The first release targets Jellyfin, with optional Radarr and Sonarr integrations. No films, TV files, accounts, metadata credentials or download-service subscriptions are included.

There is no donation account configured yet. Donations will be entirely optional and will not unlock features. Third-party metadata permissions must be confirmed separately; a donation model is not assumed to waive provider terms.

## Repository boundaries

Application code and build workflows live in a separate private repository. Public files are copied through an explicit allowlist. The maintainer's home deployment has its own configuration, database and volumes and is never exposed by this website.

Download the versioned application bundle and checksum from the [Releases page](https://github.com/HSVEOCT/reelio-releases/releases). Version 1.0.17 passed automated installation/update checks and home testing. GitHub's automatically generated source archives of **this** repository contain public distribution materials only, not the Reelio application.
