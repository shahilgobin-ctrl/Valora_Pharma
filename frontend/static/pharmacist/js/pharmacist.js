"use strict";
// Navigation is real; the business actions remain non-persistent design previews.
document.addEventListener("click", (event) => {
  const placeholder = event.target.closest('a[data-preview-only]');
  if (placeholder) {
    event.preventDefault();
    window.alert("Design preview: this feature will be connected to Django in a later stage.");
  }
  const review = event.target.closest('#rows button[data-ref]');
  if (review) {
    const path = window.location.pathname.includes('/prescriptions/')
      ? document.body.dataset.reviewUrl : document.body.dataset.orderUrl;
    window.location.assign(path);
  }
  if (event.target.closest('[data-print-receipt]')) window.print();
});
