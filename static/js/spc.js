/* SPC Campus — main JS */
'use strict';

// ── Theme ────────────────────────────────────────────────────────────────────
(function () {
  const saved = localStorage.getItem('spc-theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
})();

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  const next    = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('spc-theme', next);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = next === 'dark' ? '☀️' : '🌙';
}

// ── Toast notifications ──────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    Object.assign(container.style, {
      position: 'fixed', bottom: '1.5rem', right: '1.5rem',
      display: 'flex', flexDirection: 'column', gap: '.5rem', zIndex: 9999,
    });
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('visible'));
  setTimeout(() => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ── Dropdown menus ───────────────────────────────────────────────────────────
document.addEventListener('click', (e) => {
  const trigger = e.target.closest('[data-dropdown]');
  const openEl  = document.querySelector('.dropdown-menu.open');

  if (trigger) {
    const targetId = trigger.getAttribute('data-dropdown');
    const menu     = document.getElementById(targetId);
    if (!menu) return;
    const isOpen = menu.classList.contains('open');
    document.querySelectorAll('.dropdown-menu.open').forEach(m => m.classList.remove('open'));
    if (!isOpen) menu.classList.add('open');
    e.stopPropagation();
  } else if (openEl && !openEl.contains(e.target)) {
    openEl.classList.remove('open');
  }
});

// ── Accordion (curriculum weeks) ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.accordion-trigger').forEach(trigger => {
    trigger.addEventListener('click', () => {
      const panel = trigger.nextElementSibling;
      const isOpen = trigger.classList.contains('open');
      // Close others in the same group
      trigger.closest('.accordion-group')?.querySelectorAll('.accordion-trigger.open').forEach(t => {
        if (t !== trigger) {
          t.classList.remove('open');
          t.nextElementSibling?.classList.remove('open');
        }
      });
      trigger.classList.toggle('open', !isOpen);
      panel?.classList.toggle('open', !isOpen);
    });
  });

  // Open first accordion by default
  const first = document.querySelector('.accordion-trigger');
  if (first && !first.classList.contains('open')) {
    first.classList.add('open');
    first.nextElementSibling?.classList.add('open');
  }

  // Theme icon sync
  const btn   = document.getElementById('theme-toggle');
  const theme = localStorage.getItem('spc-theme') || 'light';
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';

  // Auto-dismiss Django messages after 4s
  document.querySelectorAll('.message[data-auto-dismiss]').forEach(el => {
    setTimeout(() => el.style.opacity = '0', 4000);
    setTimeout(() => el.remove(), 4400);
  });

  // Highlight active nav link
  const path = window.location.pathname;
  document.querySelectorAll('.admin-nav-item, .settings-nav-item').forEach(a => {
    const href = a.getAttribute('href')?.split('?')[0];
    if (href && path.startsWith(href) && href !== '/') {
      a.classList.add('active');
    }
  });
});

// ── Navbar mobile toggle ─────────────────────────────────────────────────────
function toggleMobileMenu() {
  const nav = document.getElementById('nav-links');
  if (nav) nav.classList.toggle('open');
}

// ── Language select (mobile/footer links already use href; this handles the
//    in-page selector without a full page reload for cosmetic update only)
function applyLangChange(code) {
  window.location.href = '/lang/' + code + '/';
}

// ── Course-detail: sticky sidebar height sync ────────────────────────────────
(function() {
  const sidebar = document.querySelector('.detail-sidebar');
  if (!sidebar) return;
  function sync() {
    const heroH = document.querySelector('.detail-hero')?.offsetHeight || 0;
    sidebar.style.top = Math.max(70, heroH - window.scrollY) + 'px';
  }
  window.addEventListener('scroll', sync, { passive: true });
  sync();
})();

// ── MCQ option selection ─────────────────────────────────────────────────────
document.addEventListener('change', (e) => {
  if (e.target.type === 'radio' && e.target.name?.startsWith('q')) {
    const container = e.target.closest('.mcq-options');
    if (!container) return;
    container.querySelectorAll('.mcq-option').forEach(el => el.classList.remove('selected'));
    e.target.closest('.mcq-option')?.classList.add('selected');
  }
});

// ── Search form: don't submit empty ─────────────────────────────────────────
document.querySelectorAll('form[role=search]').forEach(f => {
  f.addEventListener('submit', e => {
    const q = f.querySelector('[name=q]');
    if (q && !q.value.trim()) e.preventDefault();
  });
});

// ── Cart: AJAX add-to-cart (optional enhancement) ────────────────────────────
// Standard forms handle cart actions; no JS override needed.

// ── Paystack popup (used only when PAYSTACK_PUBLIC_KEY is available) ─────────
//    Template checkout pages POST to the Django view which redirects to Paystack.
//    This function is a fallback for inline popup if ever needed.
function paystackPop(email, amount, ref, key, callbackUrl) {
  if (typeof PaystackPop === 'undefined') {
    window.location.href = callbackUrl;
    return;
  }
  const handler = PaystackPop.setup({
    key,
    email,
    amount,
    ref,
    callback: () => { window.location.href = callbackUrl; },
    onClose: () => showToast('Payment cancelled.', 'error'),
  });
  handler.openIframe();
}

// ── Progress bar animation on scroll ────────────────────────────────────────
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const bar  = entry.target;
      const pct  = bar.getAttribute('data-pct') || '0';
      bar.querySelector('.progress-fill').style.width = pct + '%';
      observer.unobserve(bar);
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.progress-bar[data-pct]').forEach(el => observer.observe(el));

// ── Mastery ring SVG animation ───────────────────────────────────────────────
document.querySelectorAll('.mastery-ring').forEach(ring => {
  const pct    = parseFloat(ring.getAttribute('data-pct') || 0);
  const circle = ring.querySelector('.ring-fill');
  if (!circle) return;
  const r = parseFloat(circle.getAttribute('r') || 36);
  const c = 2 * Math.PI * r;
  circle.style.strokeDasharray  = c;
  circle.style.strokeDashoffset = c - (c * pct / 100);
});
