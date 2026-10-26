
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById(
        "vp-order-filter-form"
    );

    if (!form) return;

    const radios = form.querySelectorAll(
        '.vp-order-glass-group input[type="radio"]'
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

            const delay = reducedMotion.matches
                ? 0
                : 540;

            submitTimer = window.setTimeout(() => {
                form.requestSubmit();
            }, delay);
        });
    });

    form.addEventListener("submit", () => {
        if (submitTimer !== null) {
            clearTimeout(submitTimer);
            submitTimer = null;
        }
    });
});
