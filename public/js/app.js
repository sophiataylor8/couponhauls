// static/js/app.js
// Simple client-side interactions - NO Supabase, NO API keys

// Copy coupon code to clipboard
function copyCoupon(code, affUrl = '') {
  navigator.clipboard.writeText(code).then(() => {
    // Show success notification
    const notification = document.createElement('div');
    notification.className = 'fixed top-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg z-50';
    notification.innerHTML = `✅ Coupon code "${code}" copied!`;
    document.body.appendChild(notification);
    
    setTimeout(() => {
      notification.remove();
    }, 3000);
    
    // Open affiliate URL if provided
    if (affUrl) {
      setTimeout(() => {
        window.open(affUrl, '_blank', 'noopener,noreferrer');
      }, 500);
    }
  }).catch(err => {
    console.error('Failed to copy:', err);
    alert('Failed to copy code. Please try manually.');
  });
}

// Newsletter subscription (client-side only, integrate with your email service)
document.addEventListener('DOMContentLoaded', () => {
  // Homepage newsletter
  const newsletterForm = document.getElementById('newsletterForm');
  if (newsletterForm) {
    newsletterForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const email = document.getElementById('emailInput').value;
      
      // TODO: Integrate with your email service (Mailchimp, ConvertKit, etc.)
      console.log('Newsletter signup:', email);
      alert('✅ Thank you for subscribing!');
      newsletterForm.reset();
    });
  }
  
  // Store page newsletter
  const storeNewsletterForm = document.getElementById('storeNewsletterForm');
  if (storeNewsletterForm) {
    storeNewsletterForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const email = document.getElementById('storeEmailInput').value;
      
      // TODO: Integrate with your email service
      console.log('Store newsletter signup:', email);
      alert('✅ Thank you for subscribing!');
      storeNewsletterForm.reset();
    });
  }
});