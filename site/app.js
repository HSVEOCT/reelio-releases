'use strict';
const demo = document.querySelector('#demo-request');
demo.addEventListener('click', () => {
  demo.disabled = true;
  demo.textContent = '✓ Request sent';
  document.querySelector('#demo-feedback').textContent = 'A preview only. No real request was created.';
});
async function configurePage() {
  try {
    const response = await fetch('release.json', {cache: 'no-cache'});
    if (!response.ok) throw new Error('Release information unavailable');
    const release = await response.json();
    if (release.version && release.downloadUrl) {
      const url = new URL(release.downloadUrl);
      if (url.origin !== 'https://github.com' || !url.pathname.startsWith('/HSVEOCT/reelio-releases/releases/download/')) throw new Error('Invalid release URL');
      document.querySelector('#release-label').textContent = `Reelio ${release.version} · ${release.channel === 'stable' ? 'Stable release' : 'Preview release'}`;
      document.querySelector('#release-detail').textContent = release.channel === 'stable' ? 'Built, checked and tested at home. Download the bundle and follow the installation guide.' : 'An early build for testing. Keep a backup and read the release notes before installing.';
      const download = document.querySelector('#download-button');
      download.href = url.href;
      download.textContent = `Download ${release.version} ↓`;
    }
    if (release.donationUrl) {
      const url = new URL(release.donationUrl);
      if (url.protocol !== 'https:' || url.username || url.password) throw new Error('Invalid donation URL');
      const donate = document.querySelector('#donate-button');
      donate.href = url.href;
      donate.rel = 'noopener noreferrer';
      donate.hidden = false;
      document.querySelector('#donate-pending').hidden = true;
    }
  } catch (error) {
    // The server-rendered preparation state remains useful when the manifest is unavailable.
    console.info('Reelio release information is temporarily unavailable.');
  }
}
configurePage();
