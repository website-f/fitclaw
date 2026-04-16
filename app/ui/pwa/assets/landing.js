/* ═══════════════════════════════════════
   FitClaw AI Ops · Landing Page Logic
   ═══════════════════════════════════════ */

// ── Nav: add background on scroll past hero ──
const nav = document.getElementById('landNav');
const hero = document.querySelector('.land-hero');

if (nav && hero) {
  const heroObserver = new IntersectionObserver(
    ([entry]) => {
      nav.classList.toggle('scrolled', !entry.isIntersecting);
    },
    { threshold: 0.05 }
  );
  heroObserver.observe(hero);
}

// ── Scroll reveal animations ──
const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.1, rootMargin: '0px 0px -40px 0px' }
);

document.querySelectorAll('.reveal').forEach((el) => revealObserver.observe(el));

// ── Smooth scroll for anchor links ──
document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (e) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (target) {
      e.preventDefault();
      const offset = 70;
      const top = target.getBoundingClientRect().top + window.scrollY - offset;
      window.scrollTo({ top, behavior: 'smooth' });
    }
  });
});

const agentDownloadPlatforms = ['windows', 'android'];

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 100 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatTimestamp(isoString) {
  if (!isoString) return '';
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleString();
}

function setDownloadState(platform, item, fallbackMessage = '') {
  const button = document.getElementById(`landDownloadButton-${platform}`);
  const status = document.getElementById(`landDownloadStatus-${platform}`);
  const meta = document.getElementById(`landDownloadMeta-${platform}`);
  if (!button || !status || !meta) return;

  if (!item) {
    status.textContent = 'Catalog error';
    status.className = 'land-download-pill is-missing';
    meta.textContent = fallbackMessage || 'Could not read the installer catalog from the server.';
    return;
  }

  if (item.available) {
    const parts = [item.filename, formatBytes(item.size_bytes), formatTimestamp(item.updated_at)].filter(Boolean);
    status.textContent = 'Ready';
    status.className = 'land-download-pill is-ready';
    meta.textContent = parts.join(' • ');
    button.href = item.download_url || '#';
    button.setAttribute('download', item.filename || '');
    button.classList.remove('is-disabled');
    button.removeAttribute('aria-disabled');
    return;
  }

  status.textContent = 'Missing';
  status.className = 'land-download-pill is-missing';
  meta.textContent = `No ${platform === 'windows' ? '.exe' : '.apk'} build is available on this server yet.`;
  button.href = '#';
  button.removeAttribute('download');
  button.classList.add('is-disabled');
  button.setAttribute('aria-disabled', 'true');
}

async function loadAgentDownloads() {
  try {
    const response = await fetch('/api/v1/downloads/agents', { cache: 'no-store' });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const downloads = payload.downloads || {};
    agentDownloadPlatforms.forEach((platform) => {
      setDownloadState(platform, downloads[platform]);
    });
  } catch (error) {
    console.error('Failed to load agent downloads', error);
    agentDownloadPlatforms.forEach((platform) => {
      setDownloadState(platform, null, 'Could not verify builds right now. You can still refresh this page after uploading new artifacts.');
    });
  }
}

loadAgentDownloads();

// ── PWA install prompt (Chrome / Android) ──
let deferredPrompt = null;
const installBanner = document.getElementById('landInstallBanner');
const installBtn    = document.getElementById('landInstallBtn');
const dismissBtn    = document.getElementById('landInstallDismiss');

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  if (installBanner) installBanner.removeAttribute('hidden');
});

if (installBtn) {
  installBtn.addEventListener('click', async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
    if (installBanner) installBanner.setAttribute('hidden', '');
  });
}

if (dismissBtn) {
  dismissBtn.addEventListener('click', () => {
    if (installBanner) installBanner.setAttribute('hidden', '');
  });
}

// ── Register service worker ──
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/app-sw.js').catch(() => {});
  });
}
