// scripts/fetch-data.js
// Fetches data from Supabase at build time and saves as Hugo data files

require('dotenv').config(); // Load .env file
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');

// Read from environment variables
const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY; // Use service key for build

if (!SUPABASE_URL || !SUPABASE_SERVICE_KEY) {
  console.error('❌ Missing Supabase credentials in environment variables');
  console.error('');
  console.error('Please create a .env file with:');
  console.error('SUPABASE_URL=https://your-project.supabase.co');
  console.error('SUPABASE_SERVICE_KEY=your-service-role-key');
  console.error('');
  console.error('Get your credentials from: Supabase Dashboard → Settings → API');
  process.exit(1);
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_KEY);

// Create data directory if it doesn't exist
const dataDir = path.join(__dirname, '../data');
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

async function fetchStores() {
  console.log('📦 Fetching stores...');
  
  const { data: stores, error } = await supabase
    .from('stores')
    .select('*')
    .eq('is_active', true)
    .order('website_name');
  
  if (error) {
    console.error('❌ Error fetching stores:', error);
    return;
  }
  
  // Get coupon count for each store
  const storesWithCounts = await Promise.all(
    stores.map(async (store) => {
      const { count } = await supabase
        .from('coupons')
        .select('*', { count: 'exact', head: true })
        .eq('store_id', store.id)
        .eq('is_active', true);
      
      return {
        ...store,
        coupon_count: count || 0
      };
    })
  );
  
  // Save all stores
  fs.writeFileSync(
    path.join(dataDir, 'stores.json'),
    JSON.stringify(storesWithCounts, null, 2)
  );
  
  console.log(`✅ Saved ${storesWithCounts.length} stores to data/stores.json`);
  
  // Save individual store files for Hugo content
  const storesContentDir = path.join(__dirname, '../content/stores');
  if (!fs.existsSync(storesContentDir)) {
    fs.mkdirSync(storesContentDir, { recursive: true });
  }
  
  for (const store of storesWithCounts) {
    const markdown = `---
title: "${store.website_name}"
slug: "${store.slug}"
description: "${store.website_desc || ''}"
logo_url: "${store.logo_url || ''}"
website_url: "${store.website_url || ''}"
website_aff_url: "${store.website_aff_url || ''}"
is_active: ${store.is_active}
website_featured: ${store.website_featured}
coupon_count: ${store.coupon_count}
store_id: "${store.id}"
---

${store.website_desc || ''}
`;
    
    fs.writeFileSync(
      path.join(storesContentDir, `${store.slug}.md`),
      markdown
    );
  }
  
  console.log(`✅ Created ${storesWithCounts.length} store markdown files`);
  
  return storesWithCounts;
}

async function fetchCoupons(stores) {
  console.log('🎫 Fetching coupons...');
  
  const { data: coupons, error } = await supabase
    .from('coupons')
    .select('*')
    .eq('is_active', true)
    .order('created_at', { ascending: false });
  
  if (error) {
    console.error('❌ Error fetching coupons:', error);
    return;
  }
  
  // Organize coupons by store
  const couponsByStore = {};
  
  for (const coupon of coupons) {
    if (!couponsByStore[coupon.store_id]) {
      couponsByStore[coupon.store_id] = [];
    }
    couponsByStore[coupon.store_id].push(coupon);
  }
  
  // Save all coupons
  fs.writeFileSync(
    path.join(dataDir, 'coupons.json'),
    JSON.stringify(coupons, null, 2)
  );
  
  console.log(`✅ Saved ${coupons.length} coupons to data/coupons.json`);
  
  // Save coupons organized by store
  fs.writeFileSync(
    path.join(dataDir, 'coupons_by_store.json'),
    JSON.stringify(couponsByStore, null, 2)
  );
  
  console.log(`✅ Saved coupons organized by store`);
  
  // Save individual coupon files for each store
  for (const [storeId, storeCoupons] of Object.entries(couponsByStore)) {
    const store = stores.find(s => s.id === storeId);
    if (store) {
      fs.writeFileSync(
        path.join(dataDir, `coupons_${store.slug}.json`),
        JSON.stringify(storeCoupons, null, 2)
      );
    }
  }
  
  console.log(`✅ Created individual coupon files for each store`);
}

async function fetchFeaturedStores() {
  console.log('⭐ Fetching featured stores...');
  
  const { data: featured, error } = await supabase
    .from('stores')
    .select('*')
    .eq('is_active', true)
    .eq('website_featured', true)
    .limit(8);
  
  if (error) {
    console.error('❌ Error fetching featured stores:', error);
    return;
  }
  
  // Get coupon counts
  const featuredWithCounts = await Promise.all(
    featured.map(async (store) => {
      const { count } = await supabase
        .from('coupons')
        .select('*', { count: 'exact', head: true })
        .eq('store_id', store.id)
        .eq('is_active', true);
      
      return {
        ...store,
        coupon_count: count || 0
      };
    })
  );
  
  fs.writeFileSync(
    path.join(dataDir, 'featured_stores.json'),
    JSON.stringify(featuredWithCounts, null, 2)
  );
  
  console.log(`✅ Saved ${featuredWithCounts.length} featured stores`);
}

async function fetchLatestCoupons() {
  console.log('🆕 Fetching latest coupons...');
  
  const { data: coupons, error } = await supabase
    .from('coupons')
    .select(`
      *,
      stores!inner (
        website_name,
        slug,
        logo_url
      )
    `)
    .eq('is_active', true)
    .order('created_at', { ascending: false })
    .limit(6);
  
  if (error) {
    console.error('❌ Error fetching latest coupons:', error);
    return;
  }
  
  fs.writeFileSync(
    path.join(dataDir, 'latest_coupons.json'),
    JSON.stringify(coupons, null, 2)
  );
  
  console.log(`✅ Saved ${coupons.length} latest coupons`);
}

async function main() {
  console.log('🚀 Starting data fetch from Supabase...\n');
  
  try {
    const stores = await fetchStores();
    await fetchCoupons(stores);
    await fetchFeaturedStores();
    await fetchLatestCoupons();
    
    console.log('\n✨ All data fetched successfully!');
    console.log('📁 Data saved to /data directory');
    console.log('📝 Store pages created in /content/stores');
  } catch (error) {
    console.error('❌ Fatal error:', error);
    process.exit(1);
  }
}

main();