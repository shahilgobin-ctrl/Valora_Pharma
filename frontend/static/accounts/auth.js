(function () {
  "use strict";

  document.querySelectorAll("[data-password-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.getElementById(button.getAttribute("aria-controls"));
      if (!input) return;
      var showing = input.type === "password";
      input.type = showing ? "text" : "password";
      button.setAttribute("aria-pressed", String(showing));
      button.setAttribute("aria-label", showing ? "Hide password" : "Show password");
      button.classList.toggle("is-showing", showing);
    });
  });

  var summary = document.getElementById("form-errors");
  if (summary) summary.focus();
})();
