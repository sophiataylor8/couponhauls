// static/js/app.js
// CouponHauls — client-side interactions
// Store search data is lazy-loaded from JSON only when needed.

// ─── Copy coupon code ──────────────────────────────────────────────────────
function copyCoupon(code, affUrl) {
  if (!code) return;
  navigator.clipboard.writeText(code).then(function () {
    showNotification('✅ Code "' + code + '" copied!', 'success');
    if (affUrl) {
      setTimeout(function () {
        window.open(affUrl, '_blank', 'noopener,noreferrer');
      }, 600);
    }
  }).catch(function () {
    showNotification('Copy this code: ' + code, 'info');
  });
}

// ─── Notification toast ───────────────────────────────────────────────────
function showNotification(message, type) {
  type = type || 'success';
  var existing = document.getElementById('ch-notification');
  if (existing) existing.remove();

  var colors = { success: 'background:#22c55e', info: 'background:#3b82f6', error: 'background:#ef4444' };
  var el = document.createElement('div');
  el.id = 'ch-notification';
  el.style.cssText = 'position:fixed;top:1rem;right:1rem;' + (colors[type] || colors.success) +
    ';color:#fff;padding:.75rem 1.25rem;border-radius:.5rem;box-shadow:0 4px 12px rgba(0,0,0,.15);' +
    'z-index:9999;font-size:.875rem;font-weight:600;transition:opacity .3s;max-width:280px;';
  el.textContent = message;
  document.body.appendChild(el);

  setTimeout(function () {
    el.style.opacity = '0';
    setTimeout(function () { el.remove(); }, 300);
  }, 3000);
}

// ─── Lazy-load store data ─────────────────────────────────────────────────
var storesLoaded = false;
var storesLoading = false;
var storesCallbacks = [];

function loadStoresData(callback) {
  if (storesLoaded) {
    if (callback) callback(window.STORES_DATA);
    return;
  }
  if (callback) storesCallbacks.push(callback);
  if (storesLoading) return;
  storesLoading = true;

  var url = window.STORES_DATA_URL || '/stores-search-data.json';
  fetch(url)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      window.STORES_DATA = data;
      storesLoaded = true;
      storesLoading = false;
      storesCallbacks.forEach(function (cb) { cb(data); });
      storesCallbacks = [];
    })
    .catch(function (err) {
      storesLoading = false;
      console.warn('CouponHauls: could not load store data', err);
    });
}

// ─── Search stores ────────────────────────────────────────────────────────
function searchStores(query, data) {
  if (!query || !Array.isArray(data)) return [];
  var q = query.toLowerCase().trim();
  return data.filter(function (s) {
    return s.n && s.n.toLowerCase().includes(q);
  });
}

// ─── Live search dropdown ─────────────────────────────────────────────────
function initSearch() {
  var form  = document.getElementById('searchForm');
  var input = document.getElementById('storeSearch');
  if (!form || !input) return;

  // Create dropdown
  var dropdown = document.createElement('ul');
  dropdown.id = 'searchDropdown';
  dropdown.style.cssText = 'position:absolute;left:0;right:0;top:100%;margin-top:.25rem;' +
    'background:#fff;border-radius:.75rem;box-shadow:0 8px 30px rgba(0,0,0,.12);' +
    'z-index:50;display:none;max-height:16rem;overflow-y:auto;' +
    'border:1px solid #e2e8f0;list-style:none;padding:0;margin-top:.25rem;';
  input.parentElement.style.position = 'relative';
  input.parentElement.appendChild(dropdown);

  function renderDropdown(results) {
    if (!results || !results.length) {
      dropdown.style.display = 'none';
      return;
    }
    dropdown.innerHTML = results.slice(0, 8).map(function (s) {
      return '<li><a href="' + s.u + '" style="display:flex;align-items:center;gap:.75rem;' +
        'padding:.75rem 1rem;text-decoration:none;transition:background .12s;border-left:3px solid transparent;"' +
        'onmouseover="this.style.background=\'#f0f9ff\';this.style.borderLeftColor=\'#0284c7\'"' +
        'onmouseout="this.style.background=\'\';this.style.borderLeftColor=\'transparent\'">' +
        '<div style="width:2rem;height:2rem;border-radius:.5rem;background:#0284c7;' +
        'display:flex;align-items:center;justify-content:center;flex-shrink:0;">' +
        '<span style="font-size:1rem;font-weight:900;color:#fff;text-transform:uppercase;">' +
        s.n.charAt(0) + '</span></div>' +
        '<span style="font-size:.875rem;font-weight:600;color:#374151;">' + s.n + '</span>' +
        '<span style="margin-left:auto;font-size:.75rem;color:#9ca3af;">' + (s.c || 0) + ' coupons</span>' +
        '</a></li>';
    }).join('');
    dropdown.style.display = '';
  }

  // Load data when input is focused for the first time
  input.addEventListener('focus', function () {
    loadStoresData(function () {
      var q = input.value.trim();
      if (q.length >= 2) renderDropdown(searchStores(q, window.STORES_DATA));
    });
  });

  input.addEventListener('input', function () {
    var q = this.value.trim();
    if (!window.STORES_DATA) {
      loadStoresData(function (data) {
        renderDropdown(q.length >= 2 ? searchStores(q, data) : []);
      });
      return;
    }
    renderDropdown(q.length >= 2 ? searchStores(q, window.STORES_DATA) : []);
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var results = searchStores(input.value.trim(), window.STORES_DATA || []);
    window.location.href = results.length ? results[0].u : '/stores/';
  });

  document.addEventListener('click', function (e) {
    if (!form.contains(e.target)) dropdown.style.display = 'none';
  });
}

// ─── Mobile menu ──────────────────────────────────────────────────────────
function initMobileMenu() {
  var btn  = document.getElementById('mobileMenuBtn');
  var menu = document.getElementById('mobileMenu');
  if (btn && menu) {
    btn.addEventListener('click', function () {
      menu.classList.toggle('hidden');
    });
  }
}

// ─── Newsletter forms ─────────────────────────────────────────────────────
function initNewsletterForms() {
  [
    { formId: 'newsletterForm',      inputId: 'emailInput' },
    { formId: 'storeNewsletterForm', inputId: 'storeEmailInput' },
  ].forEach(function (pair) {
    var form = document.getElementById(pair.formId);
    if (!form) return;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var emailEl = document.getElementById(pair.inputId);
      if (emailEl && emailEl.value) {
        showNotification('✅ Thank you for subscribing!', 'success');
        form.reset();
      }
    });
  });
}

// ─── Init ─────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  initSearch();
  initMobileMenu();
  initNewsletterForms();
});