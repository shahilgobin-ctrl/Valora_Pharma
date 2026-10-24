// Design-preview interactions only; no server writes.

  const steps = ["Pending", "Confirmed", "Preparing", "Ready for Pickup", "Completed"];
  let current = 0;
  const select = document.getElementById("nextStatus");
  const btn = document.getElementById("applyBtn");
  const badge = document.getElementById("badge");
  const toast = document.getElementById("toast");
  const items = [...document.querySelectorAll("#timeline li")];

  function fillOptions() {
    select.innerHTML = '<option value="">Select...</option>';
    if (current < steps.length - 1) {
      const o = document.createElement("option");
      o.value = o.textContent = steps[current + 1];
      select.appendChild(o);
    }
    btn.disabled = true;
  }
  select.addEventListener("change", () => { btn.disabled = !select.value; });

  btn.addEventListener("click", () => {
    if (!select.value) return;
    current = steps.indexOf(select.value);
    const stamp = new Date().toLocaleString("en-GB", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Indian/Mauritius"
    }).replace(",", "") + " (UTC+4)";
    items.forEach((li, i) => {
      li.classList.toggle("done", i < current);
      li.classList.toggle("current", i === current);
      if (i === current && !li.querySelector(".time")) {
        li.querySelector(".label").insertAdjacentHTML("beforeend", '<span class="time">' + stamp + "</span>");
      }
    });
    badge.textContent = steps[current];
    badge.classList.remove("pop"); void badge.offsetWidth; badge.classList.add("pop");
    toast.textContent = "Status updated to " + steps[current];
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2400);
    fillOptions();
  });
  fillOptions();
