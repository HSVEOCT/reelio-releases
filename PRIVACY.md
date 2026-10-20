# Privacy and external services

Reelio runs on your server. Accounts, settings, requests and integration credentials are stored in that installation's PostgreSQL database. The public download website does not give access to anyone's Reelio instance.

Configured integrations communicate with their respective services. TMDB receives metadata searches and requests; artwork may be fetched by your browser from TMDB's image service. Jellyfin, Radarr, Sonarr and notification services receive the requests needed for the features you enable. Their own terms and privacy policies apply.

During installation and updates, Docker contacts the official image registries and Alpine package repositories to obtain runtime components. Those services receive the ordinary network requests needed for downloads.

No shared API keys, media library, download sources or subscription accounts are bundled. Never expose `.env`, database dumps or exported integration settings. Issue reports should include versions and redacted symptoms, not credentials or personal library data.

The website uses local static files and no analytics scripts. It links to GitHub for downloads and issue reporting. GitHub applies its own privacy policy. Optional support links go to Ko-fi, which has its own privacy policy. No payment form is embedded here.


## Optional installation statistics

The current installer reports successful fresh installs and updates after their health and retention checks. A daily systemd timer checks that the local Reelio API is healthy before sending an activity report to https://telemetry.harveyjs.uk. This is enabled by default, disclosed during setup, and can be disabled without affecting Reelio. Existing users start reporting only when they use a reporting-enabled installer/update helper.

Reports contain a random installation ID, a separate random authentication key, deterministic event ID, event type, UTC day, Reelio version, broad Linux distribution, architecture and virtualisation category. This is pseudonymous reporting: the ID links reports from the same installation. The collector stores only a hash of the authentication key. No usernames, emails, server names, installation paths, public application URLs, media titles, searches, requests, integration keys or hardware fingerprint are included.

The collection service does not store source IPs or user-agent strings in its database or production access logs. Cloudflare and network intermediaries process connection metadata under their own policies. Detailed events and inactive instance records expire after 90 days, with hourly cleanup while the collector and its health checks run. Anonymous daily aggregates are retained. Reports are estimates and cannot count opted-out installations or prove a unique person.

To opt out before an install or update:

```sh
sudo env REELIO_TELEMETRY=0 sh ./reelio-install.sh
```

`DO_NOT_TRACK=1` is also respected. After setup, replace the directory below with your installation path:

```sh
sudo python3 /opt/reelio/reelio-telemetry.py disable --target /opt/reelio
```

The disabled choice persists across updates. To disable and request removal of the installation record using its saved random key:

```sh
sudo python3 /opt/reelio/reelio-telemetry.py forget --target /opt/reelio
```

Deletion requires a working connection. If it fails, reporting remains disabled and the local key is kept so you can retry. Historical anonymous aggregate totals are retained. An unavailable reporting service never blocks an installation or update. See https://telemetry.harveyjs.uk/privacy for the collector disclosure.

## Voluntary developer feedback

When you press Send in **Feedback & support**, Reelio sends the report type, title, details, Reelio version, random submission reference and an optional email you enter to the developer at `https://telemetry.harveyjs.uk/v1/feedback`. The form explains this before submission. Your account email, credentials, settings and logs are not added automatically. Do not include secrets in the message.

These reports are stored in the private developer inbox, independently of optional installation statistics. They do not create installation counts and can be sent with statistics disabled. Historical reports created for your local administrator stay on your server. Developer reports and optional contact details are retained for up to 365 days with hourly cleanup while service health checks run; the developer can delete them sooner. If you provide an email, it can be used for manual follow-up. Reports are not public GitHub issues, and developer notes/status are not synchronized back to your instance. The collection service describes [reporting and retention](https://telemetry.harveyjs.uk/privacy).
