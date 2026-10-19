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

1. Create your owner account. The guided setup opens automatically.
2. Add your own TMDB credentials to enable discovery, then connect Jellyfin if you use it.
3. Optionally connect Radarr and Sonarr. Test each connection and choose from the quality profiles and root folders returned by your service.

You can skip services you do not use or pause and return through **Admin → Guided setup**. Existing installations open normally after an update; their owners can open the guide from Admin, keeping saved credentials and other settings.

Keep the server and chosen address reachable from your household's network. Create your owner account before inviting other people.

## Choose the connection that suits your setup

**Home network / LAN:** choose option 1. Reelio listens on the specific server IPv4 address you select. Open the printed address, for example `http://192.168.1.50:43834`. This is the simplest option for a homelab.

**Existing HTTPS domain:** choose option 2 if you already manage a reverse proxy and domain. The wizard saves your HTTPS address and secure-cookie settings. Point your proxy at the printed HTTP backend address. A proxy on another machine or in a container needs a reachable server address rather than the host's localhost. Forwarded headers remain untrusted unless you explicitly confirm that only your trusted proxy can reach the backend. Setup does not create DNS records, TLS certificates, router forwarding or proxy rules.

**This server only:** choose option 3 to listen on `127.0.0.1`. Open Reelio in a browser on that same server. This option is not intended for accessing a headless server from your PC.

Docker-published ports can bypass some host firewall rules. Use a specific LAN address and do not forward the port from your router for a LAN installation. See [Docker's networking guidance](https://docs.docker.com/engine/install/ubuntu/#firewall-limitations).

## Requirements

- **Linux amd64 / x86_64.** Run the installer on the Linux host, not directly on macOS, Windows or ARM.
- Root access or `sudo`.
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

Manual versioned downloads and checksums remain available on the [Releases page](https://github.com/HSVEOCT/reelio-releases/releases). The current stable release is **1.0.18**, with guided service setup in the app.
