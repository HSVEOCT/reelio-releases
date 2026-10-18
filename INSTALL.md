# Install Reelio

The first compiled release is being prepared. The instructions below apply once a release bundle is published. Cloning this repository alone does not install the application.

1. Use a Linux amd64 server with Docker Engine, Docker Compose v2, OpenSSL and available disk space. Docker-in-LXC requires a working Docker configuration on your Proxmox host.
2. Download the official `reelio-VERSION-linux-amd64.tar.gz` and its `.sha256` file from Releases. Check the archive with `sha256sum -c reelio-VERSION-linux-amd64.tar.gz.sha256`.
3. Extract it into its own directory, then run `sh install.sh` from that directory. The installer verifies the bundled files, generates a random database password, checks the host port when `ss` is available, and loads the supplied images.
4. Open `http://127.0.0.1:43834` on the Docker host. For a remote host, forward it with `ssh -L 43834:127.0.0.1:43834 USER@YOUR-SERVER` and open that address on your own computer.
5. Create the owner account. Add your own Jellyfin and metadata credentials under Admin → Integrations. Radarr and Sonarr are optional. No shared API credentials are provided.

The default host port is **43834**, configured through `REELIO_PORT`. To choose another port for a new install, run `REELIO_PORT=YOUR-UNUSED-PORT sh install.sh`. Existing applications are not modified. Availability cannot be guaranteed until checked on your target host.

By default the web service listens on loopback only. For access from a trusted LAN, set `REELIO_BIND=0.0.0.0` in `.env` and run `docker compose --env-file .env up -d`. Configure firewall rules appropriate to your network. Set up the owner before exposing access.

For a reverse proxy, configure an HTTPS hostname, `PUBLIC_URL=https://YOUR-HOSTNAME` and `SECURE_COOKIE=true`. Enable `TRUST_PROXY` only when requests can only arrive through your trusted proxy. Do not expose PostgreSQL or the API separately.

Reelio uses its own Compose project (`reelio-public`) and volumes. Do not reuse a home installation's directory or project name unless you are deliberately migrating it with a verified backup. AI coding workers and source-code mounts are not part of the public bundle.

Use Reelio with media and services you have permission to use. Provider terms apply to metadata, artwork and external services.
