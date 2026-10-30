// Scroll reveal
const io = new IntersectionObserver(entries => {
  entries.forEach(en => { if(en.isIntersecting){ en.target.classList.add('in'); io.unobserve(en.target); } });
}, {threshold:.12});
document.querySelectorAll('.reveal').forEach((el,i)=>{ el.style.transitionDelay = (i%4)*80 + 'ms'; io.observe(el); });


// Use the same authenticated, CSRF-protected cart as the shop pages.
document.getElementById('medGrid').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-product-id]');
  if (!button || button.disabled) return;
  button.disabled = true;
  try {
    const csrf = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
    const response = await fetch(document.body.dataset.cartAddUrl, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(csrf?.slice('csrftoken='.length) || '')},
      body: JSON.stringify({product_id: Number(button.dataset.productId), quantity: 1})
    });
    if (response.status === 401) {
      location.href = document.body.dataset.loginUrl + '?next=' + encodeURIComponent(location.pathname);
      return;
    }
    const cart = await response.json();
    if (!response.ok) throw new Error(cart.error || 'Unable to add this medicine.');
    const badge = document.getElementById('cartCount');
    badge.textContent = cart.item_count;
    badge.classList.toggle('show', cart.item_count > 0);
    showToast('Added to cart');
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});
let toastTimer;
function showToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}
