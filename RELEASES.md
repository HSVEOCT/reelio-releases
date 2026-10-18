# Release channels

1. The private source repository builds and checks a candidate.
2. The candidate bundle contains compiled Docker images and installation files, with an archive checksum and build manifest.
3. The maintainer tests that exact bundle in a controlled home deployment after taking a backup. A release is never described as home-tested before this happens.
4. A deliberate promotion records the candidate run, commit, archive digest, home-test confirmation and third-party licensing review.
5. The exact tested archive is published here. It is not rebuilt during promotion.

Preview releases are marked as prereleases. Stable releases are explicit promotions, never automatic deployments of every source change. Installing the latest release is a user's choice; Reelio does not silently replace a running installation.

There is no stable release yet. Until one is published, the website shows preparation status rather than linking to a nonexistent download.
