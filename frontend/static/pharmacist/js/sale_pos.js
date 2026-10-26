/* Progressive enhancement; Django remains authoritative for price and stock. */
(() => {
  "use strict";
  const form = document.querySelector("#pos-sale-form");
  if (!form) return;
  const products = JSON.parse(document.querySelector("#pos-catalogue-data").textContent);
  const owners = JSON.parse(document.querySelector("#pos-prescription-owners").textContent);
  const byId = new Map(products.map(p => [String(p.id), p]));
  const lines = document.querySelector("#pos-lines");
  const management = form.querySelector('[name="lines-TOTAL_FORMS"]');
  const money = cents => "Rs " + (cents / 100).toFixed(2);
  const cents = price => Math.round(Number(price) * 100);
  const getRows = () => [...lines.querySelectorAll(".pos-line")];
  const fields = row => ({
    medicine: row.querySelector('[name$="-medicine"]'),
    quantity: row.querySelector('[name$="-quantity"]'),
    deleted: row.querySelector('[name$="-DELETE"]')
  });
  const active = row => {
    const f = fields(row);
    return f.medicine.value && !f.deleted.checked;
  };
  let total = 0;

  function refresh() {
    total = 0;
    let count = 0, needsRx = false;
    for (const row of getRows()) {
      const f = fields(row), product = byId.get(f.medicine.value);
      const hasErrors = !!row.querySelector(".errorlist");
      row.hidden = !active(row) && !hasErrors;
      if (!active(row) || !product) continue;
      const quantity = Number(f.quantity.value);
      row.querySelector(".pos-line-name").textContent = product.name;
      row.querySelector(".pos-line-price").textContent = money(cents(product.price)) + " / " + product.unit;
      const subtotal = Number.isInteger(quantity) && quantity > 0 ? cents(product.price) * quantity : 0;
      row.querySelector(".pos-line-total").textContent = money(subtotal);
      f.quantity.setCustomValidity(Number.isInteger(quantity) && quantity > product.stock ? "Only " + product.stock + " usable units are currently shown. Refresh stock if needed." : "");
      total += subtotal;
      count += Number.isInteger(quantity) && quantity > 0 ? quantity : 0;
      needsRx ||= product.rx;
    }
    document.querySelector("#pos-total").textContent = money(total);
    document.querySelector("#pos-item-count").textContent = count + " unit" + (count === 1 ? "" : "s");
    document.querySelector("#pos-cart-empty").hidden = getRows().some(active);
    document.querySelector("#pos-rx-warning").hidden = !needsRx;
    if (needsRx) form.querySelector(".pos-customer").open = true;
    updatePayment();
  }

  function enhanceRow(row) {
    const f = fields(row);
    row.querySelector(".pos-remove").hidden = false;
    row.querySelector(".pos-remove").addEventListener("click", () => {
      f.deleted.checked = true;
      f.quantity.value = 1;
      f.quantity.setCustomValidity("");
      row.querySelectorAll(".errorlist").forEach(el => el.remove());
      refresh();
    });
    f.quantity.addEventListener("input", refresh);
    f.medicine.addEventListener("change", refresh);
  }

  function addProduct(product) {
    let row = getRows().find(r => active(r) && fields(r).medicine.value === String(product.id));
    if (row) {
      const input = fields(row).quantity;
      const next = Number(input.value || 0) + 1;
      if (next > product.stock || next > 10000) return;
      input.value = next;
    } else {
      if (getRows().filter(active).length >= 50) {
        window.alert("A sale supports up to 50 different medicines.");
        return;
      }
      row = getRows().find(r => !active(r));
      if (!row) {
        const index = Number(management.value);
        if (index >= 60) return;
        const fragment = document.createElement("template");
        fragment.innerHTML = document.querySelector("#pos-empty-line").innerHTML.replaceAll("__prefix__", String(index));
        row = fragment.content.querySelector(".pos-line");
        lines.append(row);
        management.value = index + 1;
        enhanceRow(row);
      }
      const f = fields(row);
      f.medicine.value = product.id;
      f.quantity.value = 1;
      f.deleted.checked = false;
      row.querySelectorAll(".errorlist").forEach(el => el.remove());
    }
    refresh();
  }

  const grid = document.querySelector("#pos-products");
  for (const product of products) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "pos-product";
    tile.disabled = product.stock <= 0;
    tile.dataset.category = product.category;
    tile.dataset.search = (product.name + " " + product.category).toLocaleLowerCase();
    for (const [tag, name, value] of [
      ["span", "pos-product-category", product.category],
      ["strong", "pos-product-name", product.name],
      ["span", "pos-product-price", money(cents(product.price)) + " / " + product.unit],
      ["span", "pos-stock " + (product.stock === 0 ? "is-out" : product.stock <= product.reorder ? "is-low" : ""), product.stock + " available"],
      ["span", "pos-product-rx", product.rx ? "Prescription required" : "Non-prescription"]
    ]) {
      const el = document.createElement(tag);
      el.className = name;
      el.textContent = value;
      tile.append(el);
    }
    tile.addEventListener("click", () => addProduct(product));
    grid.append(tile);
  }
  const category = document.querySelector("#pos-category");
  for (const name of [...new Set(products.map(p => p.category))].sort()) {
    const option = document.createElement("option");
    option.value = name; option.textContent = name; category.append(option);
  }
  function filterProducts() {
    const query = document.querySelector("#pos-search").value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const tile of grid.children) {
      tile.hidden = !tile.dataset.search.includes(query) || (category.value && tile.dataset.category !== category.value);
      if (!tile.hidden) visible++;
    }
    document.querySelector("#pos-product-count").textContent = visible + " medicines";
    document.querySelector("#pos-no-products").hidden = visible > 0;
  }
  document.querySelector("#pos-search").addEventListener("input", filterProducts);
  category.addEventListener("change", filterProducts);

  const customer = form.querySelector('[name="customer"]');
  const prescription = form.querySelector('[name="prescription"]');
  function filterPrescriptions() {
    for (const option of prescription.options) {
      if (!option.value) continue;
      const matching = String(owners[option.value]) === customer.value;
      option.hidden = !matching;
      option.disabled = !matching;
    }
    if (prescription.value && String(owners[prescription.value]) !== customer.value) prescription.value = "";
  }
  customer.addEventListener("change", filterPrescriptions);
  const method = form.querySelector('[name="method"]');
  const tendered = form.querySelector('[name="cash_tendered"]');
  function updatePayment() {
    const cash = method.value === "cash";
    document.querySelector("#pos-cash-field").hidden = !cash;
    // A draft may be saved before payment is entered.
    tendered.required = false;
    const difference = cents(tendered.value || "0") - total;
    document.querySelector("#pos-change").textContent = cash && tendered.value !== ""
      ? (difference < 0 ? "Short by " + money(-difference) : money(difference)) : "—";
  }
  method.addEventListener("change", updatePayment);
  tendered.addEventListener("input", updatePayment);
  form.addEventListener("submit", event => {
    if (event.submitter?.value !== "checkout") return;
    if (!getRows().some(active)) {
      event.preventDefault(); window.alert("Add at least one medicine."); return;
    }
    if (method.value === "cash" && (tendered.value === "" || cents(tendered.value) < total)) {
      event.preventDefault(); tendered.focus();
      window.alert("Enter cash tendered covering the sale total."); return;
    }
    if (!window.confirm("Record " + money(total) + " payment and complete this sale?")) event.preventDefault();
  });
  getRows().forEach(enhanceRow);
  document.querySelector(".pos").classList.add("pos-enhanced");
  document.querySelector("#pos-catalogue-tools").hidden = false;
  filterPrescriptions(); filterProducts(); refresh();
})();

