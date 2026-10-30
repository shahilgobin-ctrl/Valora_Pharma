const sidebar = document.getElementById('side');
const menuButton = document.querySelector('[data-act="menu"]');
const mobile = window.matchMedia('(max-width:900px)');
function setMenu(open) {
  sidebar.classList.toggle('open', open);
  menuButton?.setAttribute('aria-expanded', String(open));
  sidebar.inert = mobile.matches && !open;
}
menuButton?.addEventListener('click', () => setMenu(!sidebar.classList.contains('open')));
document.querySelector('[data-close-menu]')?.addEventListener('click', () => setMenu(false));
document.addEventListener('keydown', event => { if (event.key === 'Escape') setMenu(false); });
mobile.addEventListener('change', () => setMenu(false));
setMenu(false);
document.querySelector('[data-add-line]')?.addEventListener('click', () => {
  const total = document.querySelector('[name="lines-TOTAL_FORMS"]');
  if (Number(total.value) >= 100) return;
  const content = document.getElementById('empty-line').innerHTML.replaceAll('__prefix__', total.value);
  document.getElementById('order-lines').insertAdjacentHTML('beforeend', content);
  total.value = Number(total.value) + 1;
});
document.querySelector('[data-select-batch]')?.addEventListener('click', () => {
  const value = document.querySelector('[name="batch"]').value;
  if (value) { dirty = false; location.href = '?batch=' + encodeURIComponent(value); }
});
document.querySelector('[data-print]')?.addEventListener('click', () => window.print());
const form = document.querySelector('form[data-unsaved]');
let dirty = false;
form?.addEventListener('change', () => dirty = true);
form?.addEventListener('submit', () => dirty = false);
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });

// Business previews are calculated by Django. This script only displays the result.
const reviewForm = document.querySelector('form[data-review]');
const previewOutput = document.querySelector('[data-server-preview]');
const reviewDialog = document.querySelector('[data-review-dialog]');
let previewTimer, previewController, editVersion = 0, reviewedVersion = -1;
async function serverPreview(showErrors = false) {
  previewController?.abort();
  previewController = new AbortController();
  const data = new FormData(reviewForm);
  data.set('_preview', '1');
  const response = await fetch(reviewForm.action || location.href, {
    method: 'POST', body: data, signal: previewController.signal,
    headers: {'Accept': 'application/json'}
  });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Your session may have expired. Reload and sign in again.');
  const result = await response.json();
  previewOutput.textContent = result.summary || (showErrors ? result.error : "");
  if (!response.ok) throw new Error(result.error || 'Check the form.');
  return result.summary;
}
reviewForm?.addEventListener('input', () => {
  editVersion++;
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => serverPreview().catch(error => {
    if (error.name !== 'AbortError') previewOutput.textContent = '';
  }), 450);
});
document.querySelector('[data-add-line]')?.addEventListener('click', () => { editVersion++; });
reviewForm?.addEventListener('submit', async event => {
  if (reviewedVersion === editVersion) return;
  event.preventDefault();
  dirty = true;
  clearTimeout(previewTimer);
  const version = editVersion;
  try {
    const summary = await serverPreview(true);
    if (version !== editVersion) return;
    reviewDialog.querySelector('[data-review-summary]').textContent = summary;
    reviewDialog.dataset.version = String(version);
    reviewDialog.showModal();
    reviewDialog.querySelector('[data-review-close]').focus();
  } catch (error) {
    if (error.name !== 'AbortError') previewOutput.textContent = error.message;
  }
});
document.querySelector('[data-review-close]')?.addEventListener('click', () => reviewDialog.close());
document.querySelector('[data-review-confirm]')?.addEventListener('click', () => {
  const version = Number(reviewDialog.dataset.version);
  reviewDialog.close();
  if (version !== editVersion) return;
  reviewedVersion = version;
  reviewForm.requestSubmit();
});

// Keep related controls in their own section.
document.querySelectorAll('[data-auto-filter]').forEach(select => select.addEventListener('change', () => select.form.requestSubmit()));
if (location.hash === '#inventory-settings') document.getElementById('inventory-settings')?.setAttribute('open', '');
document.addEventListener('click', event => {
  document.querySelectorAll('.report-menu[open]').forEach(menu => { if (!menu.contains(event.target)) menu.removeAttribute('open'); });
});
