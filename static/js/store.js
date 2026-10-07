/* Storefront pages. One small controller per page, chosen by <body data-page>. */
(function () {
  "use strict";
  const { api, ApiError, toast, bindForm, h, money, date, setCartCount, busy } = window.EW;
  const $ = (selector, root) => (root || document).querySelector(selector);
  const page = document.body.dataset.page;
  const params = new URLSearchParams(window.location.search);
  let currentVariant = null; // the size/colour the shopper has picked on a product page

  function skeletons(host, count) {
    host.replaceChildren(...Array.from({ length: count }, () => h("li", { class: "skeleton skeleton--card" })));
  }

  function priceNode(p) {
    return p.discount_price
      ? h("p", { class: "price" }, h("span", {}, money(p.current_price)), " ", h("s", { class: "muted" }, money(p.price)))
      : h("p", { class: "price" }, money(p.current_price));
  }

  function productCard(p) {
    const media = p.image
      ? h("img", { src: p.image.url, alt: p.image.alt || p.name, loading: "lazy", width: 600, height: 750 })
      : h("div", { class: "card__blank", "aria-hidden": "true" }, "EW");
    return h("li", { class: "card" }, h("a", { href: "/product/" + p.slug + "/" },
      h("div", { class: "card__media" }, media,
        !p.in_stock ? h("span", { class: "badge card__flag" }, "Sold out") : p.is_new_arrival ? h("span", { class: "badge card__flag" }, "New") : null),
      h("h3", { class: "card__name" }, p.name), priceNode(p),
      h("div", { class: "swatches", role: "img", "aria-label": "Colours: " + p.colors.map((c) => c.name).join(", ") },
        p.colors.map((c) => { const dot = h("span", { class: "swatch", title: c.name }); dot.style.background = c.hex || "#DCCBB6"; return dot; }))));
  }

  /* ---------- home: one shelf per category, up to ten products the owner chose ---------- */
  const shelves = $("[data-home-shelves]");
  if (shelves) {
    api("/home/").then((sections) => {
      shelves.setAttribute("aria-busy", "false");
      if (!sections.length) {
        shelves.replaceChildren(h("div", { class: "empty empty--big" }, h("strong", {}, "The first drop is being prepared."),
          h("span", {}, "New tees will show here the moment they are released.")));
        return;
      }
      shelves.replaceChildren(...sections.map((section) => h("section", { class: "shelf" },
        h("header", { class: "shelf__head" }, h("h2", {}, section.category.name),
          h("a", { href: "/shop/?category=" + encodeURIComponent(section.category.slug) }, "View all")),
        h("ul", { class: "grid grid--home" }, section.products.map(productCard)))));
      const showcase = $("[data-hero-showcase]");
      const shots = sections.flatMap((section) => section.products).filter((p) => p.image).slice(0, 2);
      if (showcase && shots.length) {
        showcase.replaceChildren(...shots.map((p) => h("a", { class: "hero__shot", href: "/product/" + p.slug + "/" },
          h("img", { src: p.image.url, alt: p.image.alt || p.name, width: 600, height: 750 }),
          h("span", { class: "hero__tag" }, h("strong", {}, p.name), h("span", {}, money(p.current_price))))));
        showcase.hidden = false;
      }
    }).catch((error) => {
      shelves.replaceChildren(h("div", { class: "empty" }, error.message + " ",
        h("button", { class: "link-button", type: "button", onclick: () => window.location.reload() }, "Try again")));
    });
  }

  /* ---------- shop ---------- */
  if (page === "shop") {
    const form = $("[data-filters]"), grid = $("[data-grid]"), more = $("[data-more]"), counter = $("[data-result-count]");
    let nextUrl = null, timer = null;

    function query() {
      const q = new URLSearchParams();
      new FormData(form).forEach((value, key) => { if (value) q.set(key, value); });
      if (params.get("flag")) q.set("flag", params.get("flag"));
      if (params.get("category")) q.set("category", params.get("category"));
      return q;
    }

    async function load(append) {
      const q = query();
      if (!append) {
        history.replaceState(null, "", q.toString() ? "?" + q : window.location.pathname);
        skeletons(grid, 8);
      }
      grid.setAttribute("aria-busy", "true");
      try {
        const data = await api(append ? nextUrl : "/products/?" + q);
        const cards = data.results.map(productCard);
        if (append) grid.append(...cards); else grid.replaceChildren(...cards);
        nextUrl = data.next ? data.next.replace(/^https?:\/\/[^/]+\/api/, "") : null;
        more.hidden = !nextUrl;
        counter.textContent = data.count + (data.count === 1 ? " product" : " products");
        if (!data.count) {
          const filtered = q.toString() !== "";
          grid.replaceChildren(filtered
            ? h("li", { class: "empty" }, "Nothing matches those filters. ",
                h("button", { class: "link-button", type: "button", onclick: () => { form.reset(); history.replaceState(null, "", window.location.pathname); window.location.reload(); } }, "Clear filters"))
            : h("li", { class: "empty empty--big" }, h("strong", {}, "The first drop is being prepared."),
                h("span", {}, "New tees will show here the moment they are released. Join the list in the footer to hear first.")));
        }
      } catch (error) {
        grid.replaceChildren(h("li", { class: "empty" }, error.message + " ",
          h("button", { class: "link-button", type: "button", onclick: () => load() }, "Try again")));
      }
      grid.setAttribute("aria-busy", "false");
    }

    api("/catalog/facets/").then((facets) => {
      const fill = (name, values, label) => values.forEach((v) => form.elements[name].append(h("option", { value: v }, label ? label(v) : v)));
      fill("fit", facets.fits, (v) => v[0].toUpperCase() + v.slice(1));
      fill("size", facets.sizes);
      fill("color", facets.colors);
      ["q", "fit", "size", "color", "sort"].forEach((n) => { if (params.get(n)) form.elements[n].value = params.get(n); });
      form.elements.in_stock.checked = params.get("in_stock") === "1";
    }).catch(() => {}).finally(() => load());

    form.addEventListener("submit", (e) => { e.preventDefault(); load(); });
    form.addEventListener("change", () => load());
    form.addEventListener("reset", () => setTimeout(load, 0));
    form.elements.q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 350); });
    more.addEventListener("click", () => busy(more, () => load(true)));
  }

  /* ---------- product ---------- */
  if (page === "product") {
    const root = $(".product"), form = $("[data-buy]"), addButton = $("[data-add]"), stockNote = $("[data-stock]");
    const groups = [["fit", "Fit"], ["color", "Colour"], ["size", "Size"]];
    const chosen = {};
    let product = null;
    const notify = $('[data-form="notify"]');

    const fitLabel = (v) => (v ? v[0].toUpperCase() + v.slice(1) : "One fit");
    const matches = (variant, picks) => Object.entries(picks).every(([k, v]) => v === undefined || variant[k] === v);
    function selected() {
      if (groups.some(([key]) => chosen[key] === undefined)) return null;
      return product.variants.find((v) => matches(v, chosen)) || null;
    }

    function renderOptions() {
      const host = $("[data-options]");
      host.replaceChildren(...groups.map(([key, label]) => {
        const values = [...new Set(product.variants.map((v) => v[key]))];
        if (values.length === 1) { chosen[key] = values[0]; if (key === "fit" && !values[0]) return null; }
        return h("fieldset", { class: "options" }, h("legend", {}, label),
          h("div", { class: "options__row" }, values.map((value) => {
            const others = { ...chosen, [key]: value };
            const possible = product.variants.some((v) => matches(v, others) && v.availability !== "out");
            return h("button", {
              type: "button", class: "option" + (chosen[key] === value ? " is-on" : "") + (possible ? "" : " is-out"),
              "aria-pressed": String(chosen[key] === value), disabled: !possible && chosen[key] !== value,
              title: possible ? null : "Sold out",
              onclick: () => { chosen[key] = chosen[key] === value && values.length > 1 ? undefined : value; update(); },
            }, key === "fit" ? fitLabel(value) : value);
          })));
      }));
    }

    function update() {
      renderOptions();
      const variant = selected();
      currentVariant = variant;
      if (!variant) {
        addButton.disabled = true; addButton.textContent = "Choose your options"; stockNote.textContent = "";
        notify.hidden = true;
        return;
      }
      $("[data-price]").textContent = money(variant.price);
      const out = variant.availability === "out";
      notify.hidden = !out;
      addButton.disabled = out;
      addButton.textContent = out ? "Sold out" : "Add to cart";
      stockNote.textContent = out ? "This size and colour is sold out." : variant.left ? "Only " + variant.left + " left" : "In stock";
      stockNote.className = "stock-note" + (variant.left || out ? " stock-note--low" : "");
    }

    function renderGallery() {
      const host = $("[data-gallery]");
      if (!product.images.length) { host.replaceChildren(h("div", { class: "card__blank card__blank--tall", "aria-hidden": "true" }, "EW")); return; }
      const main = h("img", { class: "gallery__main", src: product.images[0].url, alt: product.images[0].alt || product.name, width: 900, height: 1125 });
      const thumbs = product.images.length > 1 ? h("div", { class: "gallery__thumbs" }, product.images.map((image, i) =>
        h("button", { type: "button", "aria-label": "Show photo " + (i + 1), onclick: () => { main.src = image.url; main.alt = image.alt || product.name; } },
          h("img", { src: image.url, alt: "", width: 120, height: 150, loading: "lazy" })))) : null;
      host.replaceChildren(...[main, thumbs].filter(Boolean));
    }

    api("/products/" + root.dataset.slug + "/").then((data) => {
      product = data;
      $("[data-description]").textContent = data.description || data.short_description;
      $("[data-materials]").textContent = data.materials;
      $("[data-care]").textContent = data.care_instructions;
      renderGallery();
      if (!data.variants.length) { addButton.textContent = "Not available yet"; return; }
      update();
    }).catch((error) => toast(error.message, "error"));

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const variant = selected();
      if (!variant) return;
      const label = addButton.textContent;
      addButton.textContent = "Adding\u2026";
      busy(addButton, async () => {
        const cart = await api("/cart/items/", { method: "POST", body: { variant_id: variant.id, quantity: Math.max(1, parseInt(form.elements.quantity.value, 10) || 1) } });
        setCartCount(cart.count);
        window.EW.openCartDrawer(cart);
      }).finally(() => { addButton.textContent = label; });
    });
  }

  if (page === "product") {
    const root = $(".product"), slug = root.dataset.slug, productId = Number(root.dataset.productId);
    const stars = (n) => "\u2605".repeat(n) + "\u2606".repeat(5 - n);

    /* size guide */
    const dialog = $("[data-size-guide]");
    if (dialog) {
      $("[data-size-guide-open]").addEventListener("click", () => dialog.showModal());
      $("[data-size-guide-close]").addEventListener("click", () => dialog.close());
      dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
    }

    /* back in stock */
    bindForm($('[data-form="notify"]'), async (data) => {
      if (!currentVariant) { toast("Choose a size and colour first.", "error"); return; }
      const result = await api("/back-in-stock/", { method: "POST", body: { variant_id: currentVariant.id, email: data.email || "" } });
      toast(result.message);
    });

    /* wishlist */
    const wish = $("[data-wish]");
    if (wish) {
      const paint = (on) => { wish.setAttribute("aria-pressed", String(on)); wish.textContent = on ? "Saved to wishlist" : "Save to wishlist"; };
      api("/wishlist/").then((items) => paint(items.some((p) => p.id === productId))).catch(() => {});
      wish.addEventListener("click", () => busy(wish, async () => {
        const on = wish.getAttribute("aria-pressed") === "true";
        if (on) await api("/wishlist/" + productId + "/", { method: "DELETE" });
        else await api("/wishlist/", { method: "POST", body: { product_id: productId } });
        paint(!on);
      }));
    }

    /* reviews */
    const summary = $("[data-review-summary]"), reviewList = $("[data-review-list]"), reviewForm = $('[data-form="review"]');
    async function loadReviews() {
      const r = await api("/products/" + slug + "/reviews/");
      if (r.count) {
        const rating = $("[data-rating]");
        rating.replaceChildren(h("span", { class: "stars", "aria-hidden": "true" }, stars(Math.round(r.average))), " " + r.average + " out of 5 (" + r.count + (r.count === 1 ? " review)" : " reviews)"));
        rating.hidden = false;
      }
      summary.textContent = r.count ? r.average + " out of 5 from " + r.count + (r.count === 1 ? " verified buyer" : " verified buyers")
        : "No reviews yet. Reviews come only from customers whose order was delivered.";
      reviewList.replaceChildren(...r.results.map((x) => h("li", {},
        h("p", {}, h("span", { class: "stars", "aria-label": x.rating + " out of 5" }, stars(x.rating)), " ", h("strong", {}, x.title)),
        x.comment ? h("p", {}, x.comment) : null,
        h("p", { class: "muted small" }, x.author + ", verified buyer, " + new Date(x.created_at).toLocaleDateString("en-NG", { day: "numeric", month: "short", year: "numeric" })))));
      reviewForm.hidden = !r.can_review;
      if (r.mine) {
        reviewForm.elements.rating.value = r.mine.rating; reviewForm.elements.title.value = r.mine.title; reviewForm.elements.comment.value = r.mine.comment;
        if (r.mine.status === "pending") summary.textContent += " Your review is waiting to be checked.";
      }
    }
    loadReviews().catch(() => { summary.textContent = "Reviews did not load. Refresh to try again."; });
    bindForm(reviewForm, async (data) => {
      const result = await api("/products/" + slug + "/reviews/", { method: "POST", body: { ...data, rating: Number(data.rating) } });
      toast(result.message);
      await loadReviews();
    });
  }

  /* ---------- wishlist ---------- */
  if (page === "wishlist") {
    const grid = $("[data-grid]");
    async function load() {
      const items = await api("/wishlist/");
      grid.setAttribute("aria-busy", "false");
      if (!items.length) { grid.replaceChildren(h("li", { class: "empty" }, "Nothing saved yet. ", h("a", { href: "/shop/" }, "Browse the shop"))); return; }
      grid.replaceChildren(...items.map((p) => {
        const card = productCard(p);
        card.append(h("div", { class: "actions" },
          h("a", { class: "btn btn--small", href: "/product/" + p.slug + "/" }, p.in_stock ? "Choose size and add to cart" : "View"),
          h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: (e) => busy(e.currentTarget, async () => { await api("/wishlist/" + p.id + "/", { method: "DELETE" }); await load(); }) }, "Remove")));
        return card;
      }));
    }
    load().catch((error) => grid.replaceChildren(h("li", { class: "empty" }, error.message)));
  }

  /* ---------- cart ---------- */
  if (page === "cart") {
    const list = $("[data-lines]"), summary = $("[data-summary]");

    function render(cart) {
      setCartCount(cart.count);
      list.setAttribute("aria-busy", "false");
      summary.hidden = !cart.items.length;
      if (!cart.items.length) {
        list.replaceChildren(h("li", { class: "empty" }, "Your cart is empty. ", h("a", { href: "/shop/" }, "Browse the shop")));
        return;
      }
      const change = (item, body, method) => (event) => busy(event.currentTarget, async () =>
        render(await api("/cart/items/" + item.id + "/", { method: method || "PATCH", body })));
      list.replaceChildren(...cart.items.map((item) => h("li", { class: "line" + (item.available ? "" : " line--problem") },
        item.image ? h("img", { src: item.image, alt: "", width: 96, height: 120 }) : h("div", { class: "card__blank line__blank", "aria-hidden": "true" }, "EW"),
        h("div", { class: "line__info" },
          h("a", { href: "/product/" + item.slug + "/" }, h("strong", {}, item.product)),
          h("p", { class: "muted" }, item.label),
          item.problem ? h("p", { class: "field-error" }, item.problem) : null,
          h("div", { class: "stepper" },
            h("button", { type: "button", "aria-label": "Decrease quantity", disabled: item.quantity <= 1, onclick: change(item, { quantity: item.quantity - 1 }) }, "\u2212"),
            h("span", { "aria-live": "polite" }, String(item.quantity)),
            h("button", { type: "button", "aria-label": "Increase quantity", disabled: item.quantity >= item.max_quantity, onclick: change(item, { quantity: item.quantity + 1 }) }, "+"),
            h("button", { type: "button", class: "link-button", onclick: change(item, undefined, "DELETE") }, "Remove"))),
        h("p", { class: "line__total" }, money(item.line_total)))));
      $("[data-subtotal]").textContent = money(cart.subtotal);
      $("[data-cart-problem]").hidden = !cart.has_problems;
      $("[data-checkout]").classList.toggle("is-disabled", cart.has_problems);
    }

    $("[data-checkout]").addEventListener("click", (e) => { if (e.currentTarget.classList.contains("is-disabled")) e.preventDefault(); });
    api("/cart/").then(render).catch((error) => list.replaceChildren(h("li", { class: "empty" }, error.message)));
  }

  /* ---------- checkout ---------- */
  if (page === "checkout") {
    const list = $("[data-addresses]"), payButton = $("[data-pay]"), errorBox = $("[data-checkout-error]");
    let addresses = [], addressId = null, promoCode = "";
    const promoForm = $("[data-promo]"), promoError = $("[data-promo-error]");
    const pickup = () => $('input[name="mode"]:checked').value === "pickup";
    const fail = (message) => { errorBox.textContent = message; errorBox.hidden = !message; };

    async function refreshQuote() {
      payButton.disabled = true;
      fail("");
      if (!addressId) return;
      try {
        const q = await api("/checkout/quote/", { method: "POST", body: { address_id: addressId, pickup: pickup(), promo_code: promoCode } });
        $("[data-discount-row]").hidden = !q.discount;
        $("[data-discount-label]").textContent = "Discount (" + q.promo_code + ")";
        $("[data-discount]").textContent = "\u2212" + money(q.discount);
        $("[data-mini]").replaceChildren(...q.items.map((i) => h("li", {}, h("span", {}, i.quantity + " \u00d7 " + i.product + " (" + i.label + ")"), h("span", {}, money(i.line_total)))));
        $("[data-subtotal]").textContent = money(q.subtotal);
        $("[data-ship-label]").textContent = q.shipping_method;
        $("[data-shipping]").textContent = q.shipping_fee ? money(q.shipping_fee) : "Free";
        $("[data-total]").textContent = money(q.total);
        $("[data-estimate]").textContent = q.shipping_estimate;
        if (q.has_problems) fail("Some items in your cart are no longer available. Go back to your cart to fix them.");
        payButton.disabled = q.has_problems;
        payButton.textContent = "Pay " + money(q.total);
      } catch (error) {
        if (error.fields && error.fields.promo_code && promoCode) {  // bad code: say so, then quote without it
          promoError.textContent = error.fields.promo_code.join(" ");
          promoCode = "";
          return refreshQuote();
        }
        fail(error.message);
        if (error.message === "Your cart is empty.") window.location.assign("/cart/");
      }
    }

    function renderAddresses() {
      list.setAttribute("aria-busy", "false");
      if (!addresses.length) {
        list.replaceChildren(h("li", { class: "empty" }, "Add an address to continue."));
        $("[data-new-address]").open = true;
        return;
      }
      list.replaceChildren(...addresses.map((a) => h("li", { class: "address" + (a.id === addressId ? " is-default" : "") },
        h("label", { class: "choice" },
          h("input", { type: "radio", name: "address", checked: a.id === addressId, onchange: () => { addressId = a.id; renderAddresses(); refreshQuote(); } }),
          h("span", {}, h("strong", {}, a.first_name + " " + a.last_name), h("br"), [a.line1, a.line2, a.city, a.state].filter(Boolean).join(", "), h("br"), a.phone)))));
    }

    async function loadAddresses(selectId) {
      addresses = await api("/account/addresses/");
      addressId = selectId || (addresses.find((a) => a.is_default) || addresses[0] || {}).id || null;
      renderAddresses();
      refreshQuote();
    }

    bindForm($('[data-form="address"]'), async (data, form) => {
      const created = await api("/account/addresses/", { method: "POST", body: data });
      form.closest("details").open = false;
      await loadAddresses(created.id);
    });
    promoForm.addEventListener("submit", (event) => {
      event.preventDefault();
      promoError.textContent = "";
      promoCode = promoForm.elements.promo_code.value.trim();
      refreshQuote();
    });
    document.querySelectorAll('input[name="mode"]').forEach((el) => el.addEventListener("change", refreshQuote));

    payButton.addEventListener("click", async () => {
      const label = payButton.textContent;
      payButton.disabled = true; payButton.textContent = "Starting payment\u2026"; fail("");
      try {
        const result = await api("/checkout/", { method: "POST", body: { address_id: addressId, pickup: pickup(), promo_code: promoCode } });
        window.location.assign(result.authorization_url);  // stays disabled: no double orders
      } catch (error) {
        fail(error.message);
        payButton.textContent = label;
        refreshQuote();
      }
    });
    loadAddresses().catch((error) => fail(error.message));
  }

  /* ---------- sandbox gateway (development only) ---------- */
  if (page === "sandbox") {
    const reference = $("[data-reference]").dataset.reference;
    document.querySelectorAll("[data-outcome]").forEach((button) => button.addEventListener("click", () => busy(button, async () => {
      await api("/payments/sandbox/" + reference + "/", { method: "POST", body: { outcome: button.dataset.outcome } });
      window.location.assign("/order-success/?reference=" + encodeURIComponent(reference));
    })));
  }

  /* ---------- return from payment ---------- */
  if (page === "success") {
    const title = $("[data-result-title]"), text = $("[data-result-text]"), actions = $("[data-result-actions]");
    const reference = params.get("reference") || params.get("trxref");
    const show = (heading, body, ...links) => { title.textContent = heading; text.textContent = body; actions.replaceChildren(...links); };
    const link = (href, label, ghost) => h("a", { class: "btn" + (ghost ? " btn--ghost" : ""), href }, label);

    async function check(attempt) {
      try {
        const r = await api("/payments/verify/", { method: "POST", body: { reference } });
        if (r.payment_status === "successful" && r.order_status !== "cancelled") {
          setCartCount(0);
          return show("Thank you. Your order is confirmed.", "Order " + r.order_number + " is paid (" + money(r.total) + "). We have emailed your receipt.",
            link("/account/orders/" + r.order_number + "/", "Track your order"), link("/shop/", "Keep shopping", true));
        }
        if (r.payment_status === "failed" || r.order_status === "cancelled") {
          return show("Payment did not go through", "You were not charged for order " + r.order_number + " and the items are back in stock. You can try again.",
            link("/shop/", "Back to the shop"));
        }
        if (attempt < 6) return setTimeout(() => check(attempt + 1), 3000);
        show("We are still waiting for your bank", "Order " + r.order_number + " will update on its own as soon as Paystack confirms the payment. You do not need to pay again.",
          link("/account/orders/" + r.order_number + "/", "View order"));
      } catch (error) {
        show("We could not find that payment", error.message, link("/account/", "Go to your account"));
      }
    }
    if (reference) check(1); else show("Nothing to confirm", "This page opens after a payment.", link("/shop/", "Go to the shop"));
  }

  /* ---------- customer order page ---------- */
  if (page === "order") {
    const host = $("[data-order]");
    api("/orders/" + $("[data-number]").dataset.number + "/").then((o) => {
      const a = o.shipping_address;
      host.setAttribute("aria-busy", "false");
      host.replaceChildren(
        h("div", {},
          h("p", {}, h("span", { class: "badge badge--" + o.status }, o.status_label), " ", h("span", { class: "muted" }, "Placed " + date(o.created_at))),
          h("h2", {}, "Progress"),
          h("ol", { class: "timeline" }, o.events.map((e) => h("li", {}, h("strong", {}, e.note || e.status_label), h("span", { class: "muted" }, date(e.created_at))))),
          o.tracking_number ? h("p", {}, "Tracking: ", h("strong", {}, o.tracking_number)) : null,
          h("h2", {}, o.is_pickup ? "Pickup contact" : "Delivering to"),
          h("p", {}, a.first_name + " " + a.last_name, h("br"), [a.line1, a.line2, a.city, a.state].filter(Boolean).join(", "), h("br"), a.phone)),
        h("aside", { class: "summary" },
          h("ul", { class: "mini-lines" }, o.items.map((i) => h("li", {}, h("span", {}, i.quantity + " \u00d7 " + i.product_name + " (" + i.variant_label + ")"), h("span", {}, money(i.line_total))))),
          h("dl", { class: "totals" },
            h("div", {}, h("dt", {}, "Subtotal"), h("dd", {}, money(o.subtotal))),
            o.discount ? h("div", {}, h("dt", {}, "Discount (" + o.promo_code + ")"), h("dd", {}, "\u2212" + money(o.discount))) : null,
            h("div", {}, h("dt", {}, o.shipping_method), h("dd", {}, o.shipping_fee ? money(o.shipping_fee) : "Free")),
            h("div", { class: "totals__grand" }, h("dt", {}, "Total"), h("dd", {}, money(o.total)))),
          h("p", { class: "muted" }, "Payment: " + o.payment_status_label)));
    }).catch((error) => host.replaceChildren(h("p", { class: "empty" }, error instanceof ApiError && error.status === 404 ? "We could not find that order." : error.message)));
  }
})();
