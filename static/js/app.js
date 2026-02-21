// static/js/app.js
// All client-side interactions. No Supabase, no API keys, no external dependencies.
// Store data for search is embedded by Hugo at build time (see baseof.html STORES_DATA).

// ─── Copy coupon code to clipboard ───────────────────────────────────────────
function copyCoupon(code, affUrl = '') {
  if (!code) return;
  navigator.clipboard.writeText(code).then(() => {
    showNotification(`✅ Code "${code}" copied!`, 'success');
    if (affUrl) {
      setTimeout(() => window.open(affUrl, '_blank', 'noopener,noreferrer'), 600);
    }
  }).catch(() => {
    // Fallback for browsers that block clipboard
    showNotification(`Copy this code: ${code}`, 'info');
  });
}

// ─── Notification toast ───────────────────────────────────────────────────────
function showNotification(message, type = 'success') {
  const existing = document.getElementById('ch-notification');
  if (existing) existing.remove();

  const colors = { success: 'bg-green-500', info: 'bg-blue-500', error: 'bg-red-500' };
  const el = document.createElement('div');
  el.id = 'ch-notification';
  el.className = `fixed top-4 right-4 ${colors[type] || colors.success} text-white px-6 py-3 rounded-lg shadow-lg z-50 transition-opacity duration-300`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

// ─── Search stores (uses STORES_DATA embedded by Hugo) ───────────────────────
function searchStores(query) {
  if (!query) return [];
  const q = query.toLowerCase().trim();
  const data = window.STORES_DATA;
  if (!Array.isArray(data)) return [];
  return data.filter(s => s.n && s.n.toLowerCase().includes(q));
}

// ─── Live search dropdown ─────────────────────────────────────────────────────
function initSearch() {
  const form  = document.getElementById('searchForm');
  const input = document.getElementById('storeSearch');
  if (!form || !input) return;

  // Create dropdown element
  const dropdown = document.createElement('ul');
  dropdown.id = 'searchDropdown';
  dropdown.className = 'absolute left-0 right-0 top-full mt-1 bg-white rounded-xl shadow-xl z-50 hidden max-h-64 overflow-y-auto border border-gray-100';
  input.parentElement.style.position = 'relative';
  input.parentElement.appendChild(dropdown);

  function renderDropdown(results) {
    if (!results.length) { dropdown.classList.add('hidden'); return; }
    dropdown.innerHTML = results.slice(0, 8).map(s => `
      <li>
        <a href="/${s.s}/" class="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors">
          {{/* Letter icon in search dropdown — replaces logo image */}}
          <div style="
            width:2rem;height:2rem;border-radius:0.5rem;
            background:#0284c7;display:flex;align-items:center;
            justify-content:center;flex-shrink:0;
          ">
            <span style="font-size:1rem;font-weight:900;color:#fff;text-transform:uppercase;line-height:1;">
              ${s.n.charAt(0)}
            </span>
          </div>
          <span class="text-gray-800 font-medium">${s.n}</span>
          <span class="ml-auto text-xs text-gray-400">${s.c || 0} coupons</span>
        </a>
      </li>
    `).join('');
    dropdown.classList.remove('hidden');
  }

  input.addEventListener('input', () => {
    const q = input.value.trim();
    renderDropdown(q.length >= 2 ? searchStores(q) : []);
  });

  // Submit: go to first result or /stores/ page
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const results = searchStores(input.value.trim());
    if (results.length > 0) {
      window.location.href = `/${results[0].s}/`;
    } else {
      window.location.href = `/stores/`;
    }
  });

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (!form.contains(e.target)) dropdown.classList.add('hidden');
  });
}

// ─── Mobile menu toggle ───────────────────────────────────────────────────────
function initMobileMenu() {
  const btn  = document.getElementById('mobileMenuBtn');
  const menu = document.getElementById('mobileMenu');
  if (btn && menu) {
    btn.addEventListener('click', () => menu.classList.toggle('hidden'));
  }
}

// ─── Newsletter forms ─────────────────────────────────────────────────────────
function initNewsletterForms() {
  const forms = [
    { formId: 'newsletterForm',      inputId: 'emailInput' },
    { formId: 'storeNewsletterForm', inputId: 'storeEmailInput' },
  ];
  forms.forEach(({ formId, inputId }) => {
    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const email = document.getElementById(inputId)?.value;
      if (email) {
        // TODO: integrate with Mailchimp / ConvertKit / your email provider
        console.log('Newsletter signup:', email);
        showNotification('✅ Thank you for subscribing!', 'success');
        form.reset();
      }
    });
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initSearch();
  initMobileMenu();
  initNewsletterForms();
});