// Design-preview interactions only; no server writes.

  const PAGE_SIZE = 10;
  const data = [
    ["RX-2026-01033", "Thomas Ah-Kee",    "ORD-48441", "21 Oct, 20:09"],
    ["RX-2026-01032", "Anjali Boodhoo",   "ORD-48434", "21 Oct, 20:56"],
    ["RX-2026-01029", "Ravi Seeruttun",   "ORD-48413", "21 Oct, 23:17"],
    ["RX-2026-01026", "Priya Doorgakant", "ORD-48392", "22 Oct, 01:38"],
    ["RX-2026-01025", "Jean-Marc Laval",  "ORD-48385", "22 Oct, 02:25"],
    ["RX-2026-01024", "Aisha Ramgoolam",  "ORD-48378", "22 Oct, 03:12"],
    ["RX-2026-01021", "Thomas Ah-Kee",    "ORD-48357", "22 Oct, 05:33"],
    ["RX-2026-01018", "Nadia Joomun",     "ORD-48336", "22 Oct, 07:54"],
    ["RX-2026-01017", "Ravi Seeruttun",   "ORD-48329", "22 Oct, 08:41"],
    ["RX-2026-01016", "Sophie Bégué",     "ORD-48322", "22 Oct, 09:28"],
    ["RX-2026-01014", "Kevin Mootoo",     "ORD-48308", "22 Oct, 10:15"],
    ["RX-2026-01013", "Anjali Boodhoo",   "ORD-48301", "22 Oct, 10:42"],
    ["RX-2026-01011", "Marie-Claire Pillay", "ORD-48287", "22 Oct, 11:20"],
    ["RX-2026-01009", "Dev Ramdin",       "ORD-48273", "22 Oct, 11:58"],
    ["RX-2026-01008", "Fatima Bundhun",   "ORD-48266", "22 Oct, 12:31"],
    ["RX-2026-01006", "Jean-Marc Laval",  "ORD-48252", "22 Oct, 13:04"],
    ["RX-2026-01004", "Sophie Bégué",     "ORD-48238", "22 Oct, 13:47"],
    ["RX-2026-01002", "Nadia Joomun",     "ORD-48224", "22 Oct, 14:19"]
  ].map(([ref, customer, order, time]) => ({ ref, customer, order, time, status: "Pending" }));

  const rowsEl = document.getElementById("rows");
  const emptyEl = document.getElementById("empty");
  const searchEl = document.getElementById("search");
  const statusEl = document.getElementById("status");
  const prevBtn = document.getElementById("prev");
  const nextBtn = document.getElementById("next");
  const rangeEl = document.getElementById("range");
  const pageLabel = document.getElementById("pageLabel");
  const countPill = document.getElementById("countPill");
  const toast = document.getElementById("toast");
  let page = 1;
  let toastTimer;

  function filtered() {
    const q = searchEl.value.trim().toLowerCase();
    const s = statusEl.value;
    return data.filter(r =>
      (s === "All" || r.status === s) &&
      (!q || [r.ref, r.customer, r.order].some(v => v.toLowerCase().includes(q)))
    );
  }

  function render() {
    const list = filtered();
    const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
    page = Math.min(page, pages);
    const start = (page - 1) * PAGE_SIZE;
    const slice = list.slice(start, start + PAGE_SIZE);

    rowsEl.innerHTML = slice.map((r, i) => `
      <tr class="enter" style="--i:${i}">
        <td><a href="#" class="ref">${r.ref}</a></td>
        <td>${r.customer}</td>
        <td class="muted">${r.order}</td>
        <td class="muted">${r.time} (UTC+4)</td>
        <td><span class="badge">${r.status}</span></td>
        <td class="col-action"><button class="btn" data-ref="${r.ref}">Review</button></td>
      </tr>`).join("");

    emptyEl.style.display = list.length ? "none" : "block";
    rangeEl.textContent = list.length ? `${start + 1}–${start + slice.length} of ${list.length}` : "0 results";
    pageLabel.textContent = `Page ${page} of ${pages}`;
    prevBtn.disabled = page <= 1;
    nextBtn.disabled = page >= pages;
  }

  function updatePill() {
    const n = data.filter(r => r.status === "Pending").length;
    countPill.textContent = `${n} pending`;
    countPill.classList.remove("bump");
    void countPill.offsetWidth;
    countPill.classList.add("bump");
  }

  searchEl.addEventListener("input", () => { page = 1; render(); });
  statusEl.addEventListener("change", () => { page = 1; render(); });
  prevBtn.addEventListener("click", () => { page--; render(); });
  nextBtn.addEventListener("click", () => { page++; render(); });

  rowsEl.addEventListener("click", e => {
    if (e.target.closest(".ref")) e.preventDefault();
    const btn = e.target.closest(".btn");
    if (!btn) return;
    toast.textContent = `Opening ${btn.dataset.ref} for review`;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
  });
render();
  updatePill();
