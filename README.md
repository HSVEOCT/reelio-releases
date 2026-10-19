# Reelio

A home for your family's next film night. Discover movies and shows, request missing titles and follow them into your Jellyfin library.

**[Visit the Reelio website](https://reelio.harveyjs.uk/)**

**[Reelio 1.0.18 is available to download](https://github.com/HSVEOCT/reelio-releases/releases/tag/v1.0.18).**

Reelio is free for personal, non-commercial self-hosting under the [Reelio Personal Use Licence](LICENSE.txt). The application source is private. This repository contains the public website, documentation and installation helpers; release bundles contain the compiled API, browser assets and runtime assembly files. Application source is not included.

- [Get started](INSTALL.md)
- [Updates and backups](UPDATING.md)
- [How releases are tested](RELEASES.md)
- [Privacy and integrations](PRIVACY.md)
- [Licences and third-party components](THIRD-PARTY.md)
- [Report a problem](https://github.com/HSVEOCT/reelio-releases/issues)

Requires a Linux amd64 Docker host with Docker Compose v2 and internet access during installation or an update. Docker obtains official runtime components directly from their upstream distributors. The first release targets Jellyfin, with optional Radarr and Sonarr integrations. No films, TV files, accounts, metadata credentials or download-service subscriptions are included.

## Guided setup

Run these commands in your **Linux server's terminal** (a Proxmox container console works too):

```sh
curl -fsSL https://raw.githubusercontent.com/HSVEOCT/reelio-releases/main/install.sh -o reelio-install.sh
sudo sh ./reelio-install.sh
```

If logged in as root, omit `sudo`. Choose a fresh install or an update of an existing installation. The wizard downloads the stable release directly to your server. Fresh setup asks how you want to connect; an update keeps your existing data, settings and port and makes a verified backup first. Normal LAN setup needs no SCP or tunnel. It can offer Docker installation on Ubuntu/Debian if needed. [Read the short guide](INSTALL.md) for requirements and existing installations.

After creating your owner account, the in-app guide helps connect TMDB, Jellyfin and optional Radarr/Sonarr services. Test connections, select real profiles and folders, or skip services you do not use. You can resume from **Admin → Guided setup**.

You can [support Reelio on Ko-fi](https://ko-fi.com/reelio). Donations are entirely optional and do not unlock features or buy support or source-code access. Third-party metadata permissions must be confirmed separately; a donation model is not assumed to waive provider terms.

## Repository boundaries

Application code and build workflows live in a separate private repository. Public files are copied through an explicit allowlist. The maintainer's home deployment has its own configuration, database and volumes and is never exposed by this website.

Download the versioned application bundle and checksum from the [Releases page](https://github.com/HSVEOCT/reelio-releases/releases). Version 1.0.18 passed automated installation/update checks and home testing. GitHub's automatically generated source archives of **this** repository contain public distribution materials only, not the Reelio application.
