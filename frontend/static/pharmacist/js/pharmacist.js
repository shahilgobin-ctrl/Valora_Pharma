"use strict";

// Shared action for database-backed receipts.
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-print-receipt]")) window.print();
});
