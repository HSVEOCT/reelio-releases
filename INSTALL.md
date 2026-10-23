# Install Reelio

Run the guided installer **on the Linux server where Reelio will live**. You can use its local console, the Proxmox container console, or SSH from your computer.

## Start setup

Copy these two commands into the server terminal:

```sh
curl -fsSL https://raw.githubusercontent.com/HSVEOCT/reelio-releases/main/install.sh -o reelio-install.sh
sudo sh ./reelio-install.sh
```

Already logged in as root? Run the second command without `sudo`.

The script is public, so you can [read it before running it](https://github.com/HSVEOCT/reelio-releases/blob/main/install.sh). If `curl` is missing on Ubuntu or Debian, install it first with `sudo apt-get update && sudo apt-get install -y ca-certificates curl`.

## Answer the questions

First choose **1 — Install a fresh copy** or **2 — Update an existing installation**. For an update, follow [Update Reelio and keep your data](UPDATING.md). The remaining questions below are for a fresh installation.

Press Enter to accept a suggested answer. Setup asks for:

- **Installation folder:** normally `/opt/reelio`. It must be empty and dedicated to this installation.
- **Project name:** normally `reelio-public`. Each independent installation needs a different name.
- **How you will connect:** your home network, an existing HTTPS reverse proxy, or just this server.
- **Server address:** detected automatically when possible; check it is the address you use to reach this server.
- **Port:** normally **43834**. Choose another if it is already in use. Setup checks for collisions and saves your choice for restarts and updates.
- **Licence:** review and accept the [personal, non-commercial use terms](LICENSE.txt) to continue.
- **Docker, if missing:** on Ubuntu or Debian, setup can offer to install Docker Engine and Compose from Docker's official apt repository. Existing container runtimes are not replaced.

The wizard downloads the current stable release **directly to your server**, checks its archive and file checksums, generates a private database password, prepares the runtime images and waits for healthy services. You do not need to download files on your PC, use SCP, or create an SSH tunnel for normal LAN access.

## Open Reelio

When setup finishes, open the address it prints in a browser on your computer.

1. Create your owner account.
2. Follow guided setup to connect TMDB, Jellyfin and any optional services you use, then test them. Saved settings can be changed under **Admin → Connections**.
3. If moving from another server, choose **Restore from a backup** at the start of guided setup instead.

Keep the server and chosen address reachable from your household's network. Create your owner account before inviting other people.

## Choose the connection that suits your setup

**Home network / LAN:** choose option 1. Reelio listens on the specific server IPv4 address you select. Open the printed address, for example `http://192.168.1.50:43834`. This is the simplest option for a homelab.

**Existing HTTPS domain:** choose option 2 if you already manage a reverse proxy and domain. The wizard saves your HTTPS address and secure-cookie settings. Point your proxy at the printed HTTP backend address. A proxy on another machine or in a container needs a reachable server address rather than the host's localhost. Forwarded headers remain untrusted unless you explicitly confirm that only your trusted proxy can reach the backend. Setup does not create DNS records, TLS certificates, router forwarding or proxy rules.

**This server only:** choose option 3 to listen on `127.0.0.1`. Open Reelio in a browser on that same server. This option is not intended for accessing a headless server from your PC.

Docker-published ports can bypass some host firewall rules. Use a specific LAN address and do not forward the port from your router for a LAN installation. See [Docker's networking guidance](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations).

## Requirements

- **Linux amd64 / x86_64.** Run the installer on the Linux host, not directly on macOS, Windows or ARM.
- Root/`sudo`, or an account with working Docker access and a writable installation folder.
- Internet access to GitHub, Docker Hub and Alpine's repositories during setup.
- At least 1 GiB free on both the installation filesystem and Docker storage; allow more for data, images and backups.
- Docker Engine with Compose v2. On other Linux distributions, install these before running the wizard.
- In Proxmox LXC, Docker must be allowed by your container configuration. Setup checks Docker but does not change Proxmox.

The application is supplied as compiled files. Docker obtains official runtime images and packages upstream. No application source, media, API keys or AI worker is supplied.

## If setup stops

The wizard explains the failed check. An occupied folder, existing Compose project or occupied port will not be overwritten.

If image preparation or startup fails after your settings have been saved, fix the reported problem and run the **resume command printed by setup**, for example:

```sh
sudo sh /opt/reelio/setup.sh --resume /opt/reelio
```

Resume keeps the same database password, project, address and volumes. It is only available for an unfinished guided installation; it is not an updater.

For a connection problem, check the selected address, port and network access. For an image download problem, check DNS, internet access and available disk space. Never post your `.env`, database or credentials in a public issue.

## Existing installations and manual downloads

Use [Updates and backups](UPDATING.md) to upgrade an existing installation. The fresh-install option deliberately refuses occupied folders and projects. Choose option 2 for an existing installation; supported public and JSON migration layouts retain their data and settings.

Manual versioned downloads and checksums remain available on the [Releases page](https://github.com/HSVEOCT/reelio-releases/releases). The published 1.0.17 archive retains its original installer; the guided script above works with that exact verified package without modifying the release asset.

## NAS users
The guided installer supports accounts with Docker access without root. Use a writable folder and parent, such as `$HOME/reelio`. Existing root-owned installations require their owner or an administrator. Optional daily statistics timers need an administrator; no automatic sudo is attempted for reporting.

## Browser updates (1.0.21 and later)
After upgrading to this version, the installation owner can enable the host updater once:

```sh
sudo python3 /path/to/verified/bundle/enable-web-updates.py --target /opt/reelio
```

Replace both paths for your setup. Use the verified downloaded candidate/release bundle; the app itself cannot grant host access. This requires Linux with systemd and root once, even when normal installation runs as a Docker-group user. The service prepares a private root-owned helper and mounts only its Unix socket into the API. It briefly recreates API/web to add that mount and refresh their connection, retaining the database, settings and web port. No Docker socket is mounted into the app.

Then open **Admin > Updates**, check the stable release, accept the licence and press **Back up and update**. The page reconnects while the API/web restart. Existing data is verified and the previous application is recovered on failure where possible; a database is never automatically restored. Backups and diagnostic logs are private on the server. A failed/interrupted operation that needs attention must be inspected by the server owner before another update.

Only a newer release selected by the official stable manifest can be installed. New releases do not install automatically. Hosts without systemd can continue using the guided installer/updater.

Fresh interactive installs offer to enable browser updates after Reelio is healthy. Unattended installs require the explicit `REELIO_ENABLE_WEB_UPDATES=1` setting; ordinary installations remain available without the host service.

## Full backup and restore (1.0.22 and later)

Open **Admin > Backups** to create and download a full Reelio backup. It includes accounts and password hashes, requests, watchlists, branding, application settings and saved integration credentials. Backups are private, unencrypted files: store them securely and keep a copy off the server. Downloading a backup does not include your media library files.

Enable scheduled daily backups from the same screen. The selected time is the API container's server time. Scheduled retention does not delete safety backups made before restores.

To move to a new server, install the same or a compatible newer Reelio version, create a temporary owner account, then choose **Restore from a backup** at the start of guided setup. Existing installations can use **Admin > Backups > Upload backup to restore**, or Restore beside a saved full backup.

Reelio checks the backup and shows its date, version and record counts. Type **RESTORE** to confirm replacing the current application data. A verified safety backup is required before replacement. The database replacement runs as a transaction; invalid data leaves the current application data intact and retains the safety backup.

After a successful restore, all browser sessions are signed out. Sign in using an administrator account and password from the backup. Review **Connections**, then open **Backups** and press **Resume background services** when this server is ready to use those credentials.

Full backups have the suffix `.reelio-backup.gz`. Uploads support up to 32 MiB compressed, 128 MiB uncompressed and 250,000 records. The database schema must match the installed application, and a backup from a newer Reelio version is refused. Legacy `.sql.gz` backups remain downloadable but cannot be uploaded through the browser restore flow.

Media files, Docker/environment configuration, host updater configuration, anonymous installation statistics identity, AI workspace files and earlier backup files are not included. The destination server keeps its own database credentials, storage and web port. Re-enable browser updates separately on a new host if required. Keep access to an administrator account from your backup before restoring.
