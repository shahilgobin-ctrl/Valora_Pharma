// Design-preview interactions only; no server writes.

  const orders = [
    ["VLR-20431", "Aarav Ramdin",      1, 350,  "22 Oct 2026, 22:00", "Awaiting",     "Paid",     "Pending"],
    ["VLR-20432", "Sophie Laval",      2, 1081, "22 Oct 2026, 21:13", "Not required", "Paid",     "Pending"],
    ["VLR-20433", "Kevin Ah-Chuen",    3, 1812, "22 Oct 2026, 20:26", "Verified",     "Unpaid",   "Processing"],
    ["VLR-20434", "Priya Doorgakant",  4, 2543, "22 Oct 2026, 19:39", "Verified",     "Paid",     "Ready"],
    ["VLR-20435", "Jean-Marc Lebon",   5, 3274, "22 Oct 2026, 18:52", "Rejected",     "Failed",   "Pending"],
    ["VLR-20436", "Nadia Bholah",      1, 4005, "22 Oct 2026, 18:05", "Not required", "Paid",     "Dispatched"],
    ["VLR-20437", "Ravi Sookun",       2, 536,  "22 Oct 2026, 17:18", "Verified",     "Refunded", "Completed"],
    ["VLR-20438", "Emma Rivet",        3, 1267, "22 Oct 2026, 16:31", "Awaiting",     "Paid",     "Processing"],
    ["VLR-20439", "Yash Gopaul",       4, 1998, "22 Oct 2026, 15:44", "Awaiting",     "Paid",     "Cancelled"],
    ["VLR-20440", "Chloé Perrine",     5, 2729, "22 Oct 2026, 14:57", "Not required", "Unpaid",   "Pending"]
  ];

  const cls = s => "b-" + s.toLowerCase().replace(/\s+/g, "").replace("notrequired", "notreq");
  const actionable = ["Pending", "Processing"];
  const rows = document.getElementById("rows");
  const search = document.getElementById("search");
  const chips = document.querySelectorAll(".chip");
  const empty = document.getElementById("empty");
  const showing = document.getElementById("showing");
  const toast = document.getElementById("toast");
  let status = "All";

  function render() {
    const q = search.value.trim().toLowerCase();
    const list = orders.filter(o =>
      (status === "All" || o[7] === status) &&
      (o[0].toLowerCase().includes(q) || o[1].toLowerCase().includes(q)));

    rows.innerHTML = list.map((o, i) => `
      <tr style="animation-delay:${i * 45}ms">
        <td><a class="ref" href="#">${o[0]}</a></td>
        <td><span class="cust-name">${o[1]}</span><span class="cust-meta">${o[2]} ${o[2] === 1 ? "item" : "items"} · Rs ${o[3].toLocaleString("en-US")}</span></td>
        <td>${o[4]}</td>
        <td><span class="badge ${cls(o[5])}">${o[5]}</span></td>
        <td><span class="badge ${cls(o[6])}">${o[6]}</span></td>
        <td><span class="badge ${cls(o[7])}">${o[7]}</span></td>
        <td><button class="btn ${actionable.includes(o[7]) ? "btn-primary" : "btn-ghost"}" data-ref="${o[0]}">${actionable.includes(o[7]) ? "Process" : "View"}</button></td>
      </tr>`).join("");

    empty.style.display = list.length ? "none" : "block";
    showing.textContent = (q || status !== "All")
      ? `Showing ${list.length} matching ${list.length === 1 ? "order" : "orders"}`
      : "Showing 1–10 of 47";
  }

  function setStatus(s) {
    status = s;
    chips.forEach(c => c.setAttribute("aria-pressed", c.textContent === s));
    render();
  }

  chips.forEach(c => c.addEventListener("click", () => setStatus(c.textContent)));
  document.querySelectorAll(".stat").forEach(b => b.addEventListener("click", () => setStatus(b.dataset.filter)));
  search.addEventListener("input", render);

  rows.addEventListener("click", e => {
    const btn = e.target.closest(".btn");
    if (!btn) return;
    toast.textContent = `${btn.textContent === "Process" ? "Processing" : "Viewing"} ${btn.dataset.ref}`;
    toast.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => toast.classList.remove("show"), 1800);
  });

  // Count-up on the summary cards
  document.querySelectorAll("[data-count]").forEach(el => {
    const target = +el.dataset.count;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = target; return; }
    const start = performance.now(), dur = 900;
    (function tick(now) {
      const p = Math.min((now - start) / dur, 1);
      el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(tick);
    })(start);
  });

  render();
