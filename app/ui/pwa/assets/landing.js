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
