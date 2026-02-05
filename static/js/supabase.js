const SUPABASE_URL = document.querySelector('meta[name="supabase-url"]')?.content || 'https://your-project.supabase.co';
const SUPABASE_KEY = document.querySelector('meta[name="supabase-key"]')?.content || 'your-anon-key';
const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

async function loadTrendingStores() {
  const container = document.getElementById('trendingStores');
  if (!container) return;
  try {
    const { data: stores, error } = await supabase
      .from('stores')
      .select('id, slug, website_name, website_desc, logo_url')
      .eq('is_active', true)
      .eq('website_featured', true)
      .limit(8);
    
    if (error) throw error;
    
    if (stores && stores.length > 0) {
      // Get coupon counts for each store
      const storesWithCounts = await Promise.all(
        stores.map(async (store) => {
          const { count } = await supabase
            .from('coupons')
            .select('*', { count: 'exact', head: true })
            .eq('store_id', store.id)
            .eq('is_active', true);
          return { ...store, coupon_count: count || 0 };
        })
      );
      
      container.innerHTML = storesWithCounts.map(store => `
        <a href="/stores/${store.slug}" class="coupon-card block hover:scale-105 transition-transform">
          <div class="p-6">
            <div class="w-20 h-20 mx-auto mb-4 bg-white rounded-lg shadow flex items-center justify-center">
              ${store.logo_url ? 
                `<img src="${store.logo_url}" alt="${store.website_name}" class="max-w-full max-h-full p-2">` : 
                `<div class="text-3xl font-bold text-primary-600">${store.website_name.charAt(0)}</div>`
              }
            </div>
            <h3 class="text-lg font-semibold text-center mb-2">${store.website_name}</h3>
            <p class="text-sm text-gray-600 text-center mb-3">${store.coupon_count} Coupons</p>
            <div class="text-center">
              <span class="text-primary-600 font-medium text-sm">View Deals →</span>
            </div>
          </div>
        </a>
      `).join('');
      
      document.getElementById('storeCount').textContent = `${stores.length}+`;
    }
  } catch (error) {
    console.error('Error loading stores:', error);
  }
}

async function loadLatestCoupons() {
  const container = document.getElementById('latestCoupons');
  if (!container) return;
  try {
    const { data: coupons, error } = await supabase
      .from('coupons')
      .select(`
        id,
        coupon_title,
        coupon_code,
        coupon_description,
        coupon_type,
        coupon_aff_url,
        expires_at,
        stores!inner (
          website_name,
          slug
        )
      `)
      .eq('is_active', true)
      .order('created_at', { ascending: false })
      .limit(6);
    
    if (error) throw error;
    
    if (coupons && coupons.length > 0) {
      container.innerHTML = coupons.map(coupon => `
        <div class="coupon-card">
          <div class="p-6">
            <div class="flex justify-between items-start mb-4">
              <div class="flex-1">
                <a href="/stores/${coupon.stores.slug}" class="text-primary-600 font-medium text-sm hover:underline mb-1 block">
                  ${coupon.stores.website_name}
                </a>
                <h3 class="text-xl font-semibold mb-2 text-gray-900">${coupon.coupon_title}</h3>
                <p class="text-gray-600 text-sm">${coupon.coupon_description || ''}</p>
              </div>
              <span class="bg-green-100 text-green-800 text-xs font-semibold px-3 py-1 rounded-full">
                ${coupon.coupon_type || 'Deal'}
              </span>
            </div>
            
            ${coupon.coupon_code ? `
              <div class="bg-gray-50 rounded-lg p-4 mb-4 border-2 border-dashed border-gray-300">
                <div class="flex items-center justify-between">
                  <code class="text-lg font-mono font-bold text-primary-600">${coupon.coupon_code}</code>
                  <button 
                    onclick="copyCoupon('${coupon.coupon_code}', '${coupon.coupon_aff_url || ''}')" 
                    class="bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
                  >
                    Copy Code
                  </button>
                </div>
              </div>
            ` : `
              <div class="mb-4">
                <a 
                  href="${coupon.coupon_aff_url || '#'}" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  class="block w-full bg-primary-600 hover:bg-primary-700 text-white px-4 py-3 rounded-lg text-center font-semibold transition-colors"
                >
                  Get Deal →
                </a>
              </div>
            `}
            
            <div class="flex items-center justify-between text-sm text-gray-500">
              <span>${coupon.coupon_code ? 'Code' : 'No Code Needed'}</span>
              ${coupon.expires_at ? `<span>Expires: ${new Date(coupon.expires_at).toLocaleDateString()}</span>` : '<span>No Expiration</span>'}
            </div>
          </div>
        </div>
      `).join('');
      
      document.getElementById('couponCount').textContent = `${coupons.length * 100}+`;
    }
  } catch (error) {
    console.error('Error loading coupons:', error);
  }
}

async function loadStoreCoupons(storeSlug) {
  const container = document.getElementById('storeCoupons');
  const noCoupons = document.getElementById('noCoupons');
  const countBadge = document.getElementById('storeCouponCount');
  
  if (!container) return;
  
  try {
    const { data: store, error: storeError } = await supabase
      .from('stores')
      .select('id, website_name')
      .eq('slug', storeSlug)
      .eq('is_active', true)
      .single();
    
    if (storeError) throw storeError;
    
    const { data: coupons, error } = await supabase
      .from('coupons')
      .select('*')
      .eq('store_id', store.id)
      .eq('is_active', true)
      .order('created_at', { ascending: false });
    
    if (error) throw error;
    
    if (coupons && coupons.length > 0) {
      countBadge.textContent = coupons.length;
      container.innerHTML = coupons.map(coupon => `
        <div class="coupon-card">
          <div class="p-6">
            <div class="flex justify-between items-start mb-4">
              <div class="flex-1">
                <h3 class="text-xl font-semibold mb-2 text-gray-900">${coupon.coupon_title}</h3>
                <p class="text-gray-600 text-sm">${coupon.coupon_description || ''}</p>
              </div>
              <span class="bg-green-100 text-green-800 text-xs font-semibold px-3 py-1 rounded-full">
                ${coupon.coupon_type || 'Deal'}
              </span>
            </div>
            
            ${coupon.coupon_code ? `
              <div class="bg-gray-50 rounded-lg p-4 mb-4 border-2 border-dashed border-gray-300">
                <div class="flex items-center justify-between">
                  <code class="text-lg font-mono font-bold text-primary-600">${coupon.coupon_code}</code>
                  <button 
                    onclick="copyCoupon('${coupon.coupon_code}', '${coupon.coupon_aff_url || ''}')" 
                    class="bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
                  >
                    Copy Code
                  </button>
                </div>
              </div>
            ` : `
              <div class="mb-4">
                <a 
                  href="${coupon.coupon_aff_url || '#'}" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  class="block w-full bg-primary-600 hover:bg-primary-700 text-white px-4 py-3 rounded-lg text-center font-semibold transition-colors"
                >
                  Get Deal →
                </a>
              </div>
            `}
            
            <div class="flex items-center justify-between text-sm text-gray-500">
              <span>${coupon.coupon_code ? 'Coupon Code' : 'No Code Needed'}</span>
              ${coupon.expires_at ? `<span>Expires: ${new Date(coupon.expires_at).toLocaleDateString()}</span>` : '<span>No Expiration</span>'}
            </div>
          </div>
        </div>
      `).join('');
      noCoupons.classList.add('hidden');
    } else {
      container.innerHTML = '';
      noCoupons.classList.remove('hidden');
      countBadge.textContent = '0';
    }
  } catch (error) {
    console.error('Error loading store coupons:', error);
    container.innerHTML = '<p class="text-center text-red-600">Error loading coupons. Please try again later.</p>';
  }
}

async function copyCoupon(code, affUrl = '') {
  try {
    await navigator.clipboard.writeText(code);
    
    // Show success message
    const message = document.createElement('div');
    message.className = 'fixed top-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in';
    message.innerHTML = `✅ Coupon code "${code}" copied to clipboard!`;
    document.body.appendChild(message);
    
    setTimeout(() => {
      message.remove();
    }, 3000);
    
    // Open affiliate URL if provided
    if (affUrl) {
      setTimeout(() => {
        window.open(affUrl, '_blank');
      }, 500);
    }
  } catch (error) {
    console.error('Error copying coupon:', error);
    alert('Failed to copy code. Please try again.');
  }
}

async function subscribeNewsletter(email, storeId = null) {
  try {
    // Newsletter functionality disabled
    // You can integrate with your own email service here
    console.log('Newsletter subscription:', email, storeId);
    alert('✅ Thank you for subscribing!');
    return true;
  } catch (error) {
    console.error('Error subscribing:', error);
    alert('Failed to subscribe. Please try again.');
    return false;
  }
}

async function searchStores(query) {
  try {
    const { data: stores, error } = await supabase
      .from('stores')
      .select('slug, website_name')
      .eq('is_active', true)
      .ilike('website_name', `%${query}%`)
      .limit(10);
    
    if (error) throw error;
    return stores;
  } catch (error) {
    console.error('Error searching stores:', error);
    return [];
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('trendingStores')) {
    loadTrendingStores();
    loadLatestCoupons();
  }
  
  if (typeof storeSlug !== 'undefined') {
    loadStoreCoupons(storeSlug);
  }
  
  const newsletterForm = document.getElementById('newsletterForm');
  if (newsletterForm) {
    newsletterForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('emailInput').value;
      const success = await subscribeNewsletter(email);
      if (success) newsletterForm.reset();
    });
  }
  
  const storeNewsletterForm = document.getElementById('storeNewsletterForm');
  if (storeNewsletterForm && typeof storeSlug !== 'undefined') {
    storeNewsletterForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const email = document.getElementById('storeEmailInput').value;
      const success = await subscribeNewsletter(email);
      if (success) storeNewsletterForm.reset();
    });
  }
  
  const searchForm = document.getElementById('searchForm');
  if (searchForm) {
    searchForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const query = document.getElementById('storeSearch').value;
      const stores = await searchStores(query);
      
      if (stores.length > 0) {
        window.location.href = `/stores/${stores[0].slug}`;
      } else {
        alert('No stores found matching your search.');
      }
    });
  }
});