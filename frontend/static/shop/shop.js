(() => {
  const cookie = (name) => document.cookie.split("; ")
    .find((row) => row.startsWith(`${name}=`))?.split("=").slice(1).join("=");

  const toast = (message) => {
    document.querySelector(".toast")?.remove();
    const element = document.createElement("div");
    element.className = "toast";
    element.textContent = message;
    document.body.append(element);
    setTimeout(() => element.remove(), 2600);
  };

  async function post(url, data) {
    const headers = { "X-CSRFToken": decodeURIComponent(cookie("csrftoken") || "") };
    const options = { method: "POST", credentials: "same-origin", headers };
    if (data instanceof FormData) {
      options.body = data;
    } else {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    let result = {};
    try { result = await response.json(); } catch {}
    if (!response.ok) throw new Error(result.error || "Something went wrong.");
    return result;
  }

  const syncProceedButton = (itemCount) => {
    const button = document.querySelector("#proceed-to-cart");
    if (button) button.hidden = Number(itemCount || 0) < 1;
  };

  syncProceedButton(document.querySelector(".cart-count")?.textContent);
  document.querySelectorAll(".filters select").forEach((select) => {
    select.addEventListener("change", () => select.form.requestSubmit());
  });

  document.addEventListener("click", async (event) => {
    const add = event.target.closest("[data-add-product]");
    if (add) {
      event.preventDefault();
      try {
        const cart = await post("/api/cart/add/", { product_id: add.dataset.addProduct });
        toast("Added to cart");
        const count = document.querySelector(".cart-count");
        if (count) count.textContent = cart.item_count;
        syncProceedButton(cart.item_count);
      } catch (error) {
        if (error.message === "Authentication required.") {
          location.href = `/login/?next=${encodeURIComponent(location.pathname)}`;
        } else toast(error.message);
      }
      return;
    }

    const remove = event.target.closest("[data-remove-item]");
    if (remove) {
      try {
        await post("/api/cart/remove/", { item_id: remove.dataset.removeItem });
        location.reload();
      } catch (error) { toast(error.message); }
      return;
    }

    const quantity = event.target.closest("[data-quantity]");
    if (quantity) {
      try {
        await post("/api/cart/update/", {
          item_id: quantity.dataset.quantity,
          quantity: Number(quantity.dataset.value),
        });
        location.reload();
      } catch (error) { toast(error.message); }
      return;
    }

    const checkout = event.target.closest("[data-checkout]");
    if (checkout) {
      checkout.disabled = true;
      try {
        const payload = new FormData();
        const file = document.querySelector("[data-prescription-file]")?.files?.[0];
        if (file) payload.append("prescription", file);
        const order = await post("/api/checkout/", payload);
        toast(`Order #${order.id} placed successfully`);
        setTimeout(() => location.reload(), 1200);
      } catch (error) {
        checkout.disabled = false;
        if (error.message === "Authentication required.") location.href = "/login/?next=/cart/";
        else toast(error.message);
      }
    }
  });
})();
