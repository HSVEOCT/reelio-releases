# Install Reelio

Download an official versioned release bundle from [Releases](https://github.com/HSVEOCT/reelio-releases/releases). These instructions apply to that bundle. Cloning the documentation repository does not install the application.

## Requirements

- A Linux **amd64 / x86_64** Docker host with Docker Compose v2, OpenSSL, tar, gzip and sha256sum.
- Internet access to Docker Hub and Alpine's repositories during installation and updates.
- An unused host port and disk space for runtime images, the database and backups.
- Your own credentials for the integrations you enable.

The default host port is **43834**, configurable through `REELIO_PORT`. No media, API keys, download accounts or AI coding worker are included.

The bundle contains the compiled API and browser assets, with Dockerfiles that assemble the runtime images locally. It does not redistribute Linux container images. Go, Node.js and an application source checkout are not needed on your server. Official base images and PostgreSQL are pinned by digest; runtime packages are fetched from Alpine during assembly.

Docker inside a Proxmox LXC must already work. Check `docker run --rm hello-world` first. A MacBook can transfer the archive to your Linux server; the app bundle does not run directly on macOS, Windows or ARM hosts.

## Fresh installation

1. Download `reelio-VERSION-linux-amd64.tar.gz` and its matching `.sha256` file from [official Releases](https://github.com/HSVEOCT/reelio-releases/releases). Read the licence and release notes.
2. On the Linux server, verify it with `sha256sum -c reelio-VERSION-linux-amd64.tar.gz.sha256`. Substitute the actual version in both filenames.
3. Extract the archive into a dedicated empty directory and run `sh install.sh` there.
4. The installer checks the files, project and port, creates a private `.env` with a random database password, prepares the runtime images and starts Reelio.
5. On the Docker host, open `http://127.0.0.1:43834`. For a remote host, use `ssh -N -L 43834:127.0.0.1:43834 USER@YOUR-SERVER` from your computer, then open that address there.
6. Create the owner account before allowing other people access.
7. Under **Admin → Integrations**, add and enable your own TMDB credentials for discovery. Connect Jellyfin and, optionally, Radarr, Sonarr and notifications. Test the services you enable.

Inside the installation directory, `docker compose --env-file .env ps` should show PostgreSQL, API and web healthy.

## Select the port and project once

For a fresh install you can choose a different unused port and unique project:

```sh
REELIO_PORT=YOUR-UNUSED-PORT REELIO_PROJECT=YOUR-UNIQUE-PROJECT sh install.sh
```

Replace the example values. The installer saves them in `.env`; updates retain them. The default project is `reelio-public`. It refuses existing projects or labelled volumes and checks the port when `ss` is available. Without `ss`, check availability yourself.

Every independent installation needs its own directory, project and port. Never share a live database volume with a test installation.

## LAN access

The default bind address is loopback. After owner setup, edit `REELIO_BIND` in `.env` to the server's LAN IP, or `0.0.0.0` if you intend to listen on every interface. Apply the change:

```sh
docker compose --env-file .env up -d --pull never --wait --wait-timeout 180
```

Open `http://YOUR-SERVER:YOUR-PORT`. Permit only the intended network through your firewall. PostgreSQL and the API need no separate published host ports.

## HTTPS reverse proxy

Configure an HTTPS hostname on your reverse proxy, forwarding to Reelio's web service. Set `PUBLIC_URL=https://YOUR-HOSTNAME` and `SECURE_COOKIE=true` in `.env`, then apply the Compose command above. Enable `TRUST_PROXY` only when requests arrive exclusively through your trusted proxy. Use the HTTPS hostname for login once secure cookies are enabled.

A proxy in another container cannot automatically reach the Docker host's loopback address. Choose a reachable bind address or an appropriate private Docker network for your proxy configuration.

## Troubleshooting

- **Port in use:** choose another unused port. Do not stop an unrelated app to free the default.
- **Project or .env already exists:** use the update guide for that installation. Do not delete its volumes or overwrite it with a fresh install.
- **Runtime images cannot be prepared:** check Docker Hub/Alpine connectivity, DNS, proxy settings and disk space.
- **Cannot connect remotely:** check the bind address, firewall and selected port. Loopback access requires the SSH tunnel above.
- **Empty discovery:** configure and enable your own TMDB credentials.
- **Login fails after enabling HTTPS:** use the configured HTTPS hostname and confirm the reverse proxy settings.

Keep credentials, database dumps and full configuration files out of public issue reports. See [updates and backups](UPDATING.md) before upgrading. The public installer does not automatically convert an older custom migration layout.
