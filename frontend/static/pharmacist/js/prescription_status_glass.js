
/* Valora — Animated prescription status selector */

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("prescription-filter-form");

  if (!form) return;

  const radios = form.querySelectorAll(
    '.glass-radio-group input[name="status"]'
  );

  const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  );

  let submitTimer = null;

  radios.forEach((radio) => {
    radio.addEventListener("change", () => {
      if (submitTimer !== null) {
        clearTimeout(submitTimer);
      }

      // Allow the original CSS spring animation to finish
      // before navigating to the filtered Django page.
      const delay = reducedMotion.matches ? 0 : 540;

      submitTimer = window.setTimeout(() => {
        form.requestSubmit();
      }, delay);
    });
  });

  // If the user manually searches, submit immediately.
  form.addEventListener("submit", () => {
    if (submitTimer !== null) {
      clearTimeout(submitTimer);
      submitTimer = null;
    }
  });
});


