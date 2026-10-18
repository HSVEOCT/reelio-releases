# Privacy and external services

Reelio runs on your server. Accounts, settings, requests and integration credentials are stored in that installation's PostgreSQL database. The public download website does not give access to anyone's Reelio instance.

Configured integrations communicate with their respective services. TMDB receives metadata searches and requests; artwork may be fetched by your browser from TMDB's image service. Jellyfin, Radarr, Sonarr and notification services receive the requests needed for the features you enable. Their own terms and privacy policies apply.

No shared API keys, media library, download sources or subscription accounts are bundled. Never expose `.env`, database dumps or exported integration settings. Issue reports should include versions and redacted symptoms, not credentials or personal library data.

The website uses local static files and no analytics scripts. It links to GitHub for downloads and issue reporting. GitHub applies its own privacy policy. If donation links are added, the selected payment provider will have its own privacy policy; no payment form is embedded here.
