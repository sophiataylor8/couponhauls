// scripts/csv-to-data.js
// Reads stores.csv and coupons.csv from project root
// Generates Hugo data files and content/stores markdown pages
// Run: node scripts/csv-to-data.js

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const dataDir = path.join(ROOT, 'data');
const storesContentDir = path.join(ROOT, 'content', 'stores');

// ─── Minimal CSV parser (no dependencies) ────────────────────────────────────
function parseCSV(text) {
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
  return lines.slice(1).map(line => {
    const values = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') { inQuotes = !inQuotes; continue; }
      if (ch === ',' && !inQuotes) { values.push(current.trim()); current = ''; continue; }
      current += ch;
    }
    values.push(current.trim());
    const obj = {};
    headers.forEach((h, i) => { obj[h] = values[i] ?? ''; });
    return obj;
  });
}
// ─────────────────────────────────────────────────────────────────────────────

// Ensure dirs exist
[dataDir, storesContentDir].forEach(d => {
  if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true });
});

// ── 1. Read CSVs ──────────────────────────────────────────────────────────────
const storesCSVPath  = path.join(ROOT, 'stores.csv');
const couponsCSVPath = path.join(ROOT, 'coupons.csv');

if (!fs.existsSync(storesCSVPath))  { console.error('❌ stores.csv not found in project root');  process.exit(1); }
if (!fs.existsSync(couponsCSVPath)) { console.error('❌ coupons.csv not found in project root'); process.exit(1); }

const stores  = parseCSV(fs.readFileSync(storesCSVPath,  'utf8'));
const coupons = parseCSV(fs.readFileSync(couponsCSVPath, 'utf8'));

console.log(`📦 ${stores.length} stores | 🎫 ${coupons.length} coupons`);

// ── 2. Coupon counts per store ─────────────────────────────────────────────────
const couponsByStore = {};
coupons.forEach(c => {
  const sid = c.store_id || c.storeId || c.store_slug || '';
  if (!couponsByStore[sid]) couponsByStore[sid] = [];
  couponsByStore[sid].push(c);
});

// ── 3. Enrich stores with coupon_count ────────────────────────────────────────
const storesEnriched = stores.map(s => {
  const sid = s.id || s.slug;
  return { ...s, coupon_count: (couponsByStore[sid] || []).length };
});

// ── 4. Save data/stores.json ──────────────────────────────────────────────────
fs.writeFileSync(path.join(dataDir, 'stores.json'), JSON.stringify(storesEnriched, null, 2));
console.log('✅ data/stores.json saved');

// ── 5. Save data/coupons.json ─────────────────────────────────────────────────
fs.writeFileSync(path.join(dataDir, 'coupons.json'), JSON.stringify(coupons, null, 2));
console.log('✅ data/coupons.json saved');

// ── 6. Save per-store coupon files  data/coupons_<slug>.json ─────────────────
storesEnriched.forEach(s => {
  const slug = s.slug || s.id || s.website_name?.toLowerCase().replace(/\s+/g, '-');
  const sid  = s.id || slug;
  const storeCoupons = couponsByStore[sid] || [];
  fs.writeFileSync(
    path.join(dataDir, `coupons_${slug}.json`),
    JSON.stringify(storeCoupons, null, 2)
  );
});
console.log('✅ per-store coupon files saved');

// ── 7. Featured stores (website_featured = true/1/yes) ────────────────────────
const featured = storesEnriched.filter(s => {
  const v = String(s.website_featured ?? '').toLowerCase();
  return v === 'true' || v === '1' || v === 'yes';
}).slice(0, 8);
fs.writeFileSync(path.join(dataDir, 'featured_stores.json'), JSON.stringify(featured, null, 2));
console.log('✅ data/featured_stores.json saved');

// ── 8. Latest 6 coupons (with store info embedded) ───────────────────────────
const storeMap = {};
storesEnriched.forEach(s => { storeMap[s.id || s.slug] = s; });

const latestCoupons = [...coupons]
  .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
  .slice(0, 6)
  .map(c => {
    const sid = c.store_id || c.storeId || c.store_slug || '';
    const store = storeMap[sid] || {};
    return {
      ...c,
      stores: {
        website_name: store.website_name || '',
        slug: store.slug || '',
        logo_url: store.logo_url || '',
      },
    };
  });
fs.writeFileSync(path.join(dataDir, 'latest_coupons.json'), JSON.stringify(latestCoupons, null, 2));
console.log('✅ data/latest_coupons.json saved');

// ── 9. Generate content/stores/<slug>.md pages ────────────────────────────────
storesEnriched.forEach(s => {
  const slug = s.slug || s.id || s.website_name?.toLowerCase().replace(/\s+/g, '-');
  // Escape double-quotes for YAML front-matter
  const safe = str => (str || '').replace(/"/g, '\\"');

  const md = `---
title: "${safe(s.website_name)}"
slug: "${slug}"
description: "${safe(s.website_desc || s.description || '')}"
logo_url: "${safe(s.logo_url || '')}"
website_url: "${safe(s.website_url || '')}"
website_aff_url: "${safe(s.website_aff_url || s.website_url || '')}"
is_active: ${s.is_active === 'false' || s.is_active === '0' ? 'false' : 'true'}
website_featured: ${s.website_featured === 'true' || s.website_featured === '1' || s.website_featured === 'yes' ? 'true' : 'false'}
coupon_count: ${s.coupon_count}
store_id: "${safe(s.id || slug)}"
---

${s.website_desc || s.description || ''}
`;

  fs.writeFileSync(path.join(storesContentDir, `${slug}.md`), md);
});

console.log(`✅ ${storesEnriched.length} store markdown pages created in content/stores/`);
console.log('\n✨ Done! Run: hugo server');