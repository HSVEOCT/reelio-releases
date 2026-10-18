# Licences and third-party components

## Reelio

Reelio is proprietary software, free for personal, non-commercial self-hosting under the [Reelio Personal Use Licence](LICENSE.txt). The application source repository remains private. Browser JavaScript is delivered to your browser as part of the app; source privacy is not a promise that compiled client code cannot be inspected.

The Reelio licence preserves rights granted by third-party authors and mandatory law. It does not relicense upstream components, metadata, artwork or media.

## Application dependencies

Every release includes generated `THIRD_PARTY_NOTICES.txt` files for the Go and JavaScript dependencies used by its build. They are also accessible from **Profile → About & credits** in the app. Keep those notices with copies of the application.

The app uses Go libraries and browser dependencies including React, React DOM and Lucide. Consult the versioned bundle's notices for the actual versions and terms rather than assuming this documentation is an exhaustive dependency inventory. Build-tool notices can appear alongside runtime dependency notices.

## Runtime components

Reelio's public archive contains compiled application payloads and public Dockerfiles. It does not include saved Linux, nginx or PostgreSQL container images. The installer obtains official runtime images directly, with release-specific base-image digests recorded in the bundle. Runtime packages are obtained from Alpine's repositories.

Alpine, nginx, PostgreSQL and their dependencies retain their own licences and notices. If you redistribute your assembled container images, separately review the applicable binary/source distribution requirements. Reelio's proprietary licence does not restrict upstream component rights.

Upstream references:

- [Alpine Linux](https://alpinelinux.org/)
- [nginx](https://nginx.org/en/)
- [PostgreSQL](https://www.postgresql.org/about/licence/)

## TMDB

Users supply their own TMDB credentials. TMDB's terms and attribution requirements apply independently of the Reelio licence.

The app includes TMDB's approved logo and the following notice in **Profile → About & credits**:

> This product uses the TMDB API but is not endorsed or certified by TMDB.

See the [TMDB API FAQ](https://developer.themoviedb.org/docs/faq) and [approved logos and attribution guidance](https://www.themoviedb.org/about/logos-attribution). No metadata credentials, movie artwork or media files are distributed with the download website.

Donations and paid features are not configured. Reassess provider permissions before adding a funding arrangement; customer-supplied keys do not waive provider terms.
