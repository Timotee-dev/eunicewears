/* Owner dashboard. The API enforces roles; this file only presents what the API allows. */
(function () {
  "use strict";
  const { api, toast, bindForm, h, money, date, busy } = window.EW;
  const $ = (selector, root) => (root || document).querySelector(selector);
  const page = document.body.dataset.page;
  const isAdmin = ["admin", "super_admin"].includes(document.body.dataset.role);
  const toKobo = (naira) => (naira === "" || naira === null ? null : Math.round(parseFloat(naira) * 100));
  const fromKobo = (kobo) => (kobo === null || kobo === undefined ? "" : String(kobo / 100));
  const badge = (status, label) => h("span", { class: "badge badge--" + status }, label);
  const empty = (text) => h("p", { class: "empty" }, text);

  document.querySelectorAll("[data-admin-only]").forEach((el) => { el.hidden = !isAdmin; });
  document.querySelectorAll(".dash__side nav a").forEach((a) => {
    const here = window.location.pathname;
    if (a.getAttribute("href") === here || (a.getAttribute("href") !== "/dashboard/" && a.getAttribute("href") !== "/" && here.startsWith(a.getAttribute("href")))) a.setAttribute("aria-current", "page");
  });

  function table(headers, rows) {
    return h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {}, headers.map((t) => h("th", { scope: "col" }, t)))),
      h("tbody", {}, rows.map((cells) => h("tr", {}, cells.map((c) => h("td", {}, c)))))));
  }

  function orderRows(orders) {
    return orders.map((o) => [h("a", { href: "/dashboard/orders/" + o.number + "/" }, o.number), o.customer, badge(o.status, o.status_label), money(o.total), date(o.created_at)]);
  }
  const ORDER_HEADERS = ["Order", "Customer", "Status", "Total", "Placed"];

  /* Paged list with search/filter form and a "Show more" button. */
  function pagedList(path, headers, toRows, emptyText) {
    const form = $("[data-filters]"), host = $("[data-table]"), more = $("[data-more]");
    let next = null, rows = [], timer = null;
    async function load(append) {
      const q = new URLSearchParams();
      new FormData(form).forEach((v, k) => { if (v) q.set(k, v); });
      try {
        const data = await api(append ? next : path + "?" + q);
        rows = append ? rows.concat(data.results) : data.results;
        next = data.next ? data.next.replace(/^https?:\/\/[^/]+\/api/, "") : null;
        more.hidden = !next;
        host.setAttribute("aria-busy", "false");
        host.replaceChildren(rows.length ? table(headers, toRows(rows)) : empty(emptyText));
      } catch (error) { host.replaceChildren(empty(error.message)); }
    }
    form.addEventListener("submit", (e) => { e.preventDefault(); load(); });
    form.addEventListener("change", () => load());
    form.elements.q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 350); });
    more.addEventListener("click", () => busy(more, () => load(true)));
    load();
  }

  /* ---------- overview ---------- */
  if (page === "overview") {
    api("/admin/stats/").then((s) => {
      const tile = (label, value, href) => h(href ? "a" : "div", { class: "tile", href }, h("span", { class: "tile__label" }, label), h("strong", {}, value));
      const tiles = $("[data-tiles]");
      tiles.setAttribute("aria-busy", "false");
      tiles.replaceChildren(
        tile("Revenue today", money(s.revenue.today)), tile("Last 7 days", money(s.revenue.week)),
        tile("Last 30 days", money(s.revenue.month)), tile("All time", money(s.revenue.all_time)),
        tile("Orders to fulfil", String(s.orders.to_fulfil), "/dashboard/orders/?status=paid"),
        tile("Awaiting payment", String(s.orders.awaiting_payment)), tile("Customers", String(s.customers)),
        tile("Low stock items", String(s.low_stock_count)));
      const peak = Math.max(1, ...s.daily_revenue.map((d) => d.revenue));
      $("[data-bars]").replaceChildren(...s.daily_revenue.map((d) => {
        const bar = h("div", { class: "bar__fill" });
        bar.style.height = Math.max(2, (d.revenue / peak) * 100) + "%";
        return h("div", { class: "bar", title: money(d.revenue) }, h("span", { class: "bar__value" }, d.revenue ? money(d.revenue) : ""), bar,
          h("span", { class: "bar__label" }, new Date(d.date).toLocaleDateString("en-NG", { weekday: "short" })));
      }));
      $("[data-low]").replaceChildren(s.low_stock.length
        ? table(["Item", "Left"], s.low_stock.map((v) => [h("a", { href: "/dashboard/products/" + v.product_id + "/" }, v.product + " (" + v.label + ")"), String(v.stock)]))
        : empty("Everything is well stocked."));
      $("[data-top]").replaceChildren(s.top_products.length
        ? table(["Product", "Units", "Revenue"], s.top_products.map((p) => [p.product_name, String(p.units), money(p.revenue)]))
        : empty("No paid orders yet."));
      $("[data-recent]").replaceChildren(s.recent_orders.length ? table(ORDER_HEADERS, orderRows(s.recent_orders)) : empty("No orders yet."));
    }).catch((error) => toast(error.message, "error"));
  }

  /* ---------- orders ---------- */
  if (page === "orders") {
    const preset = new URLSearchParams(window.location.search).get("status");
    if (preset) $("[data-filters]").elements.status.value = preset;
    const presetQ = new URLSearchParams(window.location.search).get("q");
    if (presetQ) $("[data-filters]").elements.q.value = presetQ;
    pagedList("/admin/orders/", ORDER_HEADERS, orderRows, "No orders match.");
  }

  if (page === "order") {
    const host = $("[data-order]"), number = host.dataset.number;
    function render(o) {
      const a = o.shipping_address;
      const statusForm = o.next_statuses.length ? h("form", { class: "form" },
        h("p", { class: "form-error", role: "alert", hidden: true, "data-form-error": "" }),
        h("div", { class: "field" }, h("label", { for: "next" }, "Move to"), h("select", { id: "next", name: "status" }, o.next_statuses.map((s) => h("option", { value: s.value }, s.label)))),
        h("div", { class: "field" }, h("label", { for: "track" }, "Tracking number or rider contact"), h("input", { id: "track", name: "tracking_number", value: o.tracking_number }), h("p", { class: "field-error", "data-error-for": "tracking_number" })),
        h("div", { class: "field" }, h("label", { for: "note" }, "Note for the customer (optional)"), h("input", { id: "note", name: "note", maxLength: 200 })),
        h("button", { class: "btn", type: "submit", "data-busy-label": "Updating" }, "Update status")) : h("p", { class: "muted" }, "This order is closed.");
      const notes = h("form", { class: "form" },
        h("div", { class: "field" }, h("label", { for: "internal" }, "Internal notes (never shown to the customer)"), h("textarea", { id: "internal", name: "internal_notes", rows: 3, value: o.internal_notes })),
        h("button", { class: "btn btn--ghost", type: "submit", "data-busy-label": "Saving" }, "Save notes"));
      host.setAttribute("aria-busy", "false");
      host.replaceChildren(
        h("section", {}, h("h2", {}, "Status"), h("p", {}, badge(o.status, o.status_label), " ", h("span", { class: "muted" }, "Payment: " + o.payment_status)), statusForm),
        h("section", {}, h("h2", {}, "Customer"),
          h("p", {}, o.customer, h("br"), o.email, h("br"), o.phone),
          h("h3", {}, o.is_pickup ? "Pickup" : "Deliver to"),
          h("p", {}, (a.first_name || "") + " " + (a.last_name || ""), h("br"), [a.line1, a.line2, a.city, a.state].filter(Boolean).join(", "), h("br"), a.delivery_instructions || ""), notes),
        h("section", { class: "dash__wide" }, h("h2", {}, "Items"),
          table(["Item", "SKU", "Price", "Qty", "Total"], o.items.map((i) => [i.product_name + " (" + i.variant_label + ")", i.sku, money(i.unit_price), String(i.quantity), money(i.line_total)])),
          h("dl", { class: "totals totals--narrow" },
            h("div", {}, h("dt", {}, "Subtotal"), h("dd", {}, money(o.subtotal))),
            o.discount ? h("div", {}, h("dt", {}, "Discount (" + o.promo_code + ")"), h("dd", {}, "\u2212" + money(o.discount))) : null,
            h("div", {}, h("dt", {}, o.shipping_method), h("dd", {}, money(o.shipping_fee))),
            h("div", { class: "totals__grand" }, h("dt", {}, "Total"), h("dd", {}, money(o.total))))),
        h("section", {}, h("h2", {}, "Payments"), o.payments.length
          ? table(["Reference", "Via", "Amount", "Status"], o.payments.map((p) => [p.reference, p.provider, money(p.amount), p.status])) : empty("No payment attempts.")),
        h("section", {}, h("h2", {}, "History"),
          h("ol", { class: "timeline" }, o.events.map((e) => h("li", {}, h("strong", {}, e.note || e.status_label), h("span", { class: "muted" }, date(e.created_at) + " by " + e.actor + (e.is_public ? "" : " (internal)")))))));
      if (o.next_statuses.length) bindForm(statusForm, async (data) => { render(await api("/admin/orders/" + number + "/status/", { method: "POST", body: data })); toast("Order updated."); });
      bindForm(notes, async (data) => { await api("/admin/orders/" + number + "/", { method: "PATCH", body: data }); toast("Notes saved."); });
    }
    api("/admin/orders/" + number + "/").then(render).catch((error) => host.replaceChildren(empty(error.message)));
  }

  /* ---------- products ---------- */
  if (page === "products") {
    pagedList("/admin/products/", ["Product", "Category", "Price", "Stock", "Visibility"], (products) => products.map((p) => [
      h("a", { href: "/dashboard/products/" + p.id + "/" }, p.name), p.category_name,
      p.discount_price ? money(p.discount_price) + " (was " + money(p.price) + ")" : money(p.price),
      String(p.total_stock), p.is_published ? "Published" : "Draft"]), "No products yet. Add your first one.");
  }

  if (page === "product") {
    const root = $("[data-product-id]"), form = $('[data-form="product"]');
    let id = root.dataset.productId;
    const FLAGS = ["is_published", "is_new_arrival", "is_best_seller"];

    function fill(p) {
      ["name", "short_description", "description", "materials", "care_instructions"].forEach((n) => { form.elements[n].value = p[n] || ""; });
      form.elements.category.value = p.category;
      form.elements.price.value = fromKobo(p.price);
      form.elements.discount_price.value = fromKobo(p.discount_price);
      FLAGS.forEach((n) => { form.elements[n].checked = p[n]; });
      renderImages(p.images);
      renderVariants(p.variants);
    }

    function renderImages(images) {
      const save = (ids) => api("/admin/products/" + id + "/images/reorder/", { method: "POST", body: { ids } }).then(renderImages);
      $("[data-images]").replaceChildren(...(images.length ? images.map((image, i) => h("li", {},
        h("img", { src: image.url, alt: image.alt, width: 120, height: 150 }),
        h("div", { class: "actions" },
          h("button", { class: "btn btn--ghost btn--small", type: "button", disabled: i === 0, "aria-label": "Move photo earlier",
            onclick: (e) => busy(e.currentTarget, () => { const ids = images.map((x) => x.id); ids.splice(i - 1, 0, ids.splice(i, 1)[0]); return save(ids); }) }, "Earlier"),
          h("button", { class: "btn btn--ghost btn--small", type: "button",
            onclick: (e) => busy(e.currentTarget, async () => { await api("/admin/images/" + image.id + "/", { method: "DELETE" }); renderImages(images.filter((x) => x.id !== image.id)); }) }, "Remove")),
        i === 0 ? h("span", { class: "badge" }, "Main photo") : null)) : [h("li", { class: "empty" }, "No photos yet. The first photo is the one shoppers see in the shop.")]));
    }

    function renderVariants(variants) {
      const host = $("[data-variants]");
      if (!variants.length) { host.replaceChildren(empty("No sizes yet, so the shop shows this as sold out. Open the box below, tick the sizes, type the colours and press Add to stock.")); return; }
      host.replaceChildren(table(["Fit", "Size", "Colour", "SKU", "Stock", "Add or remove stock", "On sale"], variants.map((v) => {
        const input = h("input", { type: "number", "aria-label": "Units to add (negative removes)", placeholder: "+10 or -2", class: "input--small" });
        const refresh = (updated) => renderVariants(variants.map((x) => (x.id === updated.id ? updated : x)));
        return [v.fit ? v.fit[0].toUpperCase() + v.fit.slice(1) : "One fit", v.size, v.color, v.sku,
          h("strong", { class: v.stock <= v.low_stock_threshold ? "stock-note--low" : "" }, String(v.stock)),
          h("div", { class: "stepper" }, input, h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: (e) => busy(e.currentTarget, async () => {
            const delta = parseInt(input.value, 10);
            if (!delta) { toast("Enter how many units to add or remove.", "error"); return; }
            refresh(await api("/admin/variants/" + v.id + "/stock/", { method: "POST", body: { delta } }));
            toast("Stock updated.");
          }) }, "Apply")),
          h("input", { type: "checkbox", checked: v.is_active, disabled: !isAdmin, "aria-label": "Available for sale",
            onchange: async (e) => { try { refresh(await api("/admin/variants/" + v.id + "/", { method: "PATCH", body: { is_active: e.target.checked } })); } catch (error) { toast(error.message, "error"); e.target.checked = !e.target.checked; } } })];
      })));
    }

    /* Read the simple "sizes, colours, quantity" fields from a form. */
    function sizeChoices(source) {
      const sizes = Array.from(source.querySelectorAll('input[name="size_opt"]:checked')).map((el) => el.value);
      const colors = source.elements.colors.value.split(",").map((c) => c.trim()).filter(Boolean);
      const problem = !sizes.length ? "Tick at least one size." : !colors.length ? "Type at least one colour, for example Black." : null;
      return { problem, body: { fit: source.elements.fit.value, sizes, colors, quantity: parseInt(source.elements.quantity.value, 10) || 0 } };
    }
    async function uploadPhotos(productId, files, note) {
      let failed = 0;
      for (let i = 0; i < files.length; i += 1) {
        if (note) note("Uploading photo " + (i + 1) + " of " + files.length + "\u2026");
        const body = new FormData();
        body.append("image", files[i]);
        try { await api("/admin/products/" + productId + "/images/", { method: "POST", body }); } catch (error) { failed += 1; }
      }
      return failed;
    }

    const showEditor = () => document.querySelectorAll("[data-after-create]").forEach((el) => { el.hidden = false; });

    api("/admin/categories/").then(async (categories) => {
      form.elements.category.replaceChildren(...categories.map((c) => h("option", { value: c.id }, c.name)));
      if (!categories.length) toast("Create a category first (Tees is added by the demo seed).", "error");
      if (id) { fill(await api("/admin/products/" + id + "/")); showEditor(); $("[data-archive]").hidden = !isAdmin; }
    }).catch((error) => toast(error.message, "error"));

    bindForm(form, async (data) => {
      const body = {
        name: data.name, category: Number(data.category), price: toKobo(data.price), discount_price: toKobo(data.discount_price),
        short_description: data.short_description, description: data.description, materials: data.materials,
        care_instructions: data.care_instructions, is_published: data.is_published, is_new_arrival: data.is_new_arrival, is_best_seller: data.is_best_seller,
      };
      if (id) { fill(await api("/admin/products/" + id + "/", { method: "PATCH", body })); toast("Product saved."); return; }

      // New product: details, then every size and colour with stock, then photos. One button does all three.
      const choice = sizeChoices(form);
      if (choice.problem) { throw new window.EW.ApiError(400, { error: { message: choice.problem } }); }
      const progress = $("[data-progress]"), say = (text) => { progress.hidden = false; progress.textContent = text; };
      say("Saving the product\u2026");
      const created = await api("/admin/products/", { method: "POST", body });
      id = String(created.id); // if a later step fails, pressing Save again updates this product instead of making a second one
      try {
        say("Adding sizes and stock\u2026");
        await api("/admin/products/" + created.id + "/sizes/", { method: "POST", body: choice.body });
        const failed = await uploadPhotos(created.id, Array.from(form.elements.photos.files), say);
        if (failed) window.alert(failed + " photo(s) could not be uploaded. Use JPG, PNG or WebP under 5 MB. You can add them on the next page.");
      } finally {
        window.location.assign("/dashboard/products/" + created.id + "/");
      }
    });

    bindForm($('[data-form="image"]'), async (data, imageForm) => {
      const failed = await uploadPhotos(id, Array.from(imageForm.elements.image.files));
      imageForm.reset();
      renderImages((await api("/admin/products/" + id + "/")).images);
      toast(failed ? failed + " photo(s) could not be uploaded. Use JPG, PNG or WebP under 5 MB." : "Photos uploaded.", failed ? "error" : undefined);
    });

    bindForm($('[data-form="sizes"]'), async (data, sizesForm) => {
      const choice = sizeChoices(sizesForm);
      if (choice.problem) { throw new window.EW.ApiError(400, { error: { message: choice.problem } }); }
      renderVariants((await api("/admin/products/" + id + "/sizes/", { method: "POST", body: choice.body })).variants);
      sizesForm.elements.colors.value = "";
      toast("Stock added.");
    });

    $("[data-archive]").addEventListener("click", (e) => {
      if (!window.confirm("Archive this product? It leaves the shop but stays in past orders.")) return;
      busy(e.currentTarget, async () => { await api("/admin/products/" + id + "/", { method: "DELETE" }); window.location.assign("/dashboard/products/"); });
    });
  }

  /* ---------- shared: editable list (one small form per record, plus an "add" form) ---------- */
  function editor(host, path, fields, labels) {
    const read = (form) => {
      const body = {};
      fields.forEach((f) => {
        if (f.type === "info") return;
        const el = form.elements[f.name];
        if (f.type === "checkbox") body[f.name] = el.checked;
        else if (f.type === "money") body[f.name] = el.value === "" ? (f.zero ? 0 : null) : toKobo(el.value);
        else if (f.type === "number") body[f.name] = el.value === "" ? (f.zero ? 0 : null) : Number(el.value);
        else if (f.type === "date") body[f.name] = el.value || null;
        else body[f.name] = el.value;
      });
      return body;
    };
    function control(f, record, uid) {
      const value = record ? record[f.name] : f.initial;
      if (f.type === "info") return record ? h("p", { class: "editor__info" }, f.render(record)) : null;
      const id = uid + "-" + f.name;
      if (f.type === "checkbox") return h("label", { class: "check field--check" }, h("input", { type: "checkbox", name: f.name, checked: value === undefined ? true : value, disabled: !isAdmin }), f.label);
      const input = f.type === "select"
        ? h("select", { id, name: f.name, disabled: !isAdmin }, f.options.map(([v, label]) => h("option", { value: v, selected: v === value }, label)))
        : h("input", { id, name: f.name, disabled: !isAdmin, type: f.type === "money" || f.type === "number" ? "number" : f.type === "date" ? "date" : "text",
            step: f.type === "money" ? "0.01" : null, min: f.type === "money" || f.type === "number" ? "0" : null,
            value: value === null || value === undefined ? "" : f.type === "money" ? fromKobo(value) : String(value) });
      return h("div", { class: "field" }, h("label", { for: id }, f.label), input);
    }
    function rowForm(record) {
      const uid = "e" + Math.random().toString(36).slice(2, 8);
      const form = h("form", { class: "editor__row" + (record ? "" : " editor__row--new"), novalidate: true },
        fields.map((f) => control(f, record, uid)),
        isAdmin ? h("button", { class: "btn btn--small" + (record ? " btn--ghost" : ""), type: "submit", "data-busy-label": "Saving" }, record ? "Save" : labels.add) : null);
      bindForm(form, async () => {
        await api(record ? path + record.id + "/" : path, { method: record ? "PATCH" : "POST", body: read(form) });
        toast(record ? "Saved." : labels.added);
        await load();
      });
      return form;
    }
    async function load() {
      try {
        const rows = await api(path);
        host.setAttribute("aria-busy", "false");
        host.replaceChildren(h("div", { class: "editor" }, rows.length ? rows.map(rowForm) : empty(labels.empty), isAdmin ? rowForm(null) : null));
      } catch (error) { host.replaceChildren(empty(error.message)); }
    }
    return load();
  }

  /* ---------- analytics ---------- */
  if (page === "analytics") {
    const form = $("[data-range]"), NS = "http://www.w3.org/2000/svg";
    const iso = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    const svg = (tag, attrs, text) => { const el = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v)); if (text) el.textContent = text; return el; };

    function chart(host, series, key, format) {
      const W = 720, H = 220, left = 8, bottom = 22, top = 16;
      const peak = Math.max(1, ...series.map((d) => d[key]));
      const step = (W - left * 2) / series.length, barWidth = Math.max(1, step * 0.72);
      const root = svg("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": "Bar chart, peak " + format(peak) });
      root.append(svg("line", { x1: left, x2: W - left, y1: H - bottom, y2: H - bottom }), svg("line", { x1: left, x2: W - left, y1: top, y2: top }),
        svg("text", { x: left, y: top - 4 }, format(peak)));
      series.forEach((d, i) => {
        const height = (d[key] / peak) * (H - bottom - top);
        const bar = svg("rect", { x: left + i * step + (step - barWidth) / 2, y: H - bottom - height, width: barWidth, height: Math.max(height, d[key] ? 1 : 0) });
        bar.append(svg("title", {}, d.date + ": " + format(d[key])));
        root.append(bar);
      });
      const label = (i, anchor) => root.append(svg("text", { x: left + i * step + step / 2, y: H - 6, "text-anchor": anchor }, series[i].date.slice(5)));
      label(0, "start");
      if (series.length > 2) label(Math.floor(series.length / 2), "middle");
      if (series.length > 1) label(series.length - 1, "end");
      host.replaceChildren(root);
    }

    async function load() {
      const q = new URLSearchParams({ from: form.elements.from.value, to: form.elements.to.value });
      try {
        const a = await api("/admin/analytics/?" + q);
        form.elements.from.value = a.from; form.elements.to.value = a.to;
        const tile = (label, value) => h("div", { class: "tile" }, h("span", { class: "tile__label" }, label), h("strong", {}, value));
        const tiles = $("[data-tiles]");
        tiles.setAttribute("aria-busy", "false");
        tiles.replaceChildren(tile("Revenue", money(a.totals.revenue)), tile("Paid orders", String(a.totals.orders)),
          tile("Average order", money(a.totals.average_order)), tile("Units sold", String(a.totals.units)),
          tile("Discounts given", money(a.totals.discounts)), tile("Delivery fees", money(a.totals.shipping)), tile("New customers", String(a.totals.new_customers)));
        chart($('[data-chart="revenue"]'), a.series, "revenue", money);
        chart($('[data-chart="orders"]'), a.series, "orders", String);
        const fillTable = (sel, rows, headers, toCells, none) => $(sel).replaceChildren(rows.length ? table(headers, rows.map(toCells)) : empty(none));
        fillTable("[data-top]", a.top_products, ["Product", "Units", "Revenue"], (p) => [p.product_name, String(p.units), money(p.revenue)], "No sales in this period.");
        fillTable("[data-categories]", a.by_category, ["Category", "Units", "Revenue"], (c) => [c.category, String(c.units), money(c.revenue)], "No sales in this period.");
        fillTable("[data-customers]", a.top_customers, ["Customer", "Orders", "Spent"], (c) => [c.email, String(c.orders), money(c.spent)], "No sales in this period.");
        fillTable("[data-promos]", a.promo_codes, ["Code", "Orders", "Discount"], (c) => [c.promo_code, String(c.orders), money(c.discount)], "No codes used in this period.");
      } catch (error) { toast(error.message, "error"); }
    }
    form.querySelectorAll("[data-days]").forEach((button) => button.addEventListener("click", () => {
      const end = new Date(), start = new Date();
      if (button.dataset.days === "year") start.setMonth(0, 1); else start.setDate(end.getDate() - (Number(button.dataset.days) - 1));
      form.elements.from.value = iso(start); form.elements.to.value = iso(end);
      load();
    }));
    form.addEventListener("submit", (e) => { e.preventDefault(); load(); });
    load();
  }

  /* ---------- customers ---------- */
  if (page === "customers") {
    pagedList("/admin/customers/", ["Customer", "Email", "Phone", "Joined", "Paid orders", "Spent", "Account"], (customers) => customers.map((c) => {
      const toggle = h("button", { class: "btn btn--ghost btn--small", type: "button" }, c.is_active ? "Disable" : "Enable");
      const state = h("span", {}, c.is_active ? "Active " : "Disabled ");
      toggle.addEventListener("click", () => {
        if (c.is_active && !window.confirm("Disable " + c.email + "? They will not be able to sign in.")) return;
        busy(toggle, async () => {
          const updated = await api("/admin/customers/" + c.id + "/active/", { method: "POST", body: { is_active: !c.is_active } });
          c.is_active = updated.is_active;
          toggle.textContent = c.is_active ? "Disable" : "Enable"; state.textContent = c.is_active ? "Active " : "Disabled ";
        });
      });
      return [c.name, c.email, c.phone || "", date(c.date_joined), h("a", { href: "/dashboard/orders/?q=" + encodeURIComponent(c.email) }, String(c.orders)), money(c.spent), h("div", { class: "stepper" }, state, toggle)];
    }), "No customers match.");
  }

  /* ---------- reviews ---------- */
  if (page === "reviews") {
    const form = $("[data-filters]"), list = $("[data-reviews]");
    const stars = (n) => "\u2605".repeat(n) + "\u2606".repeat(5 - n);
    async function load() {
      try {
        const data = await api("/admin/reviews/?status=" + form.elements.status.value);
        list.setAttribute("aria-busy", "false");
        if (!data.results.length) { list.replaceChildren(h("li", { class: "empty" }, "No reviews here.")); return; }
        const act = (label, run) => h("button", { class: "btn btn--ghost btn--small", type: "button", onclick: (e) => busy(e.currentTarget, async () => { await run(); await load(); }) }, label);
        const setStatus = (r, status) => () => api("/admin/reviews/" + r.id + "/", { method: "PATCH", body: { status } });
        list.replaceChildren(...data.results.map((r) => h("li", {},
          h("p", {}, h("span", { class: "stars", "aria-label": r.rating + " out of 5" }, stars(r.rating)), " ", h("strong", {}, r.title || "(no headline)"), " ", badge(r.status, r.status)),
          h("p", {}, r.comment || "(no text)"),
          h("p", { class: "muted small" }, r.product + ", by " + r.email + ", " + date(r.created_at)),
          h("div", { class: "actions" },
            r.status !== "approved" ? act("Approve", setStatus(r, "approved")) : null,
            r.status !== "hidden" ? act("Hide", setStatus(r, "hidden")) : null,
            act("Delete", async () => { if (window.confirm("Delete this review for good?")) await api("/admin/reviews/" + r.id + "/", { method: "DELETE" }); })))));
      } catch (error) { list.replaceChildren(h("li", { class: "empty" }, error.message)); }
    }
    form.addEventListener("change", load);
    load();
  }

  /* ---------- marketing ---------- */
  if (page === "marketing") {
    editor($("[data-promos]"), "/admin/promo-codes/", [
      { name: "code", label: "Code", type: "text" },
      { name: "percent_off", label: "Percent off", type: "number" },
      { name: "amount_off", label: "or amount off (\u20a6)", type: "money" },
      { name: "min_order", label: "Minimum order (\u20a6)", type: "money", zero: true },
      { name: "max_discount", label: "Largest discount (\u20a6)", type: "money" },
      { name: "starts_on", label: "Starts", type: "date" },
      { name: "ends_on", label: "Ends", type: "date" },
      { name: "usage_limit", label: "Total uses allowed", type: "number" },
      { name: "per_customer_limit", label: "Uses per customer", type: "number", initial: 1 },
      { name: "is_active", label: "Active", type: "checkbox" },
      { type: "info", render: (p) => "Used " + p.times_used + (p.times_used === 1 ? " time, " : " times, ") + money(p.discount_given) + " given in discounts" },
    ], { add: "Create code", added: "Promo code created.", empty: "No promo codes yet." });
    api("/admin/newsletter/").then((n) => { $("[data-subscribers]").textContent = String(n.active); }).catch(() => {});
  }

  /* ---------- content ---------- */
  if (page === "content") {
    const host = $("[data-content]");
    api("/admin/content/").then((blocks) => {
      host.setAttribute("aria-busy", "false");
      host.replaceChildren(...blocks.map((block) => {
        const form = h("form", { class: "form", novalidate: true },
          h("p", { class: "form-error", role: "alert", hidden: true, "data-form-error": "" }),
          block.fields.map((f) => {
            const id = block.key + "-" + f.name;
            return h("div", { class: "field" }, h("label", { for: id }, f.label),
              f.multiline ? h("textarea", { id, name: f.name, rows: f.max > 2000 ? 12 : 4, maxLength: f.max, value: block.value[f.name] || "" })
                : h("input", { id, name: f.name, maxLength: f.max, value: block.value[f.name] || "" }),
              h("p", { class: "field-error", "data-error-for": f.name }));
          }),
          h("button", { class: "btn", type: "submit", "data-busy-label": "Saving" }, "Save " + block.label.toLowerCase()));
        bindForm(form, async (data) => { await api("/admin/content/" + block.key + "/", { method: "PUT", body: data }); toast(block.label + " saved."); });
        return h("details", { class: "disclosure content-block" }, h("summary", {}, block.label), form);
      }));
    }).catch((error) => host.replaceChildren(empty(error.message)));
  }

  /* ---------- settings ---------- */
  if (page === "settings") {
    editor($("[data-shipping]"), "/admin/shipping-methods/", [
      { name: "name", label: "Name shown at checkout", type: "text" },
      { name: "zone", label: "Zone", type: "select", initial: "lagos", options: [["lagos", "Lagos"], ["other_states", "Other Nigerian states"], ["international", "International"], ["pickup", "Pickup"]] },
      { name: "fee", label: "Fee (\u20a6)", type: "money", zero: true },
      { name: "free_over", label: "Free above (\u20a6)", type: "money" },
      { name: "estimate", label: "Delivery time", type: "text" },
      { name: "is_active", label: "Active", type: "checkbox" },
    ], { add: "Add rate", added: "Delivery rate added.", empty: "No delivery rates yet. Checkout cannot work without one." });
    editor($("[data-categories]"), "/admin/categories/", [
      { name: "name", label: "Name", type: "text" },
      { name: "position", label: "Order in menus", type: "number", zero: true },
      { name: "is_active", label: "Shown in shop", type: "checkbox" },
    ], { add: "Add category", added: "Category added.", empty: "No categories yet." });
  }

  /* ---------- home page picks: ten slots per category; change a slot to swap the product ---------- */
  if (page === "home") {
    const host = $("[data-home-picks]");
    function render(categories) {
      host.setAttribute("aria-busy", "false");
      if (!categories.length) { host.replaceChildren(empty("Add a category first, under Settings.")); return; }
      host.replaceChildren(...categories.map((category) => {
        if (!category.products.length) {
          return h("section", {}, h("h2", {}, category.name), empty("No published products in this category yet. Add and publish some under Products."));
        }
        const slots = Array.from({ length: category.limit }, (_, i) => {
          const id = "pick-" + category.id + "-" + i;
          const select = h("select", { id, disabled: !isAdmin },
            h("option", { value: "" }, "Empty"),
            category.products.map((p) => h("option", { value: p.id, selected: category.picks[i] === p.id }, p.name)));
          return h("li", { class: "slot" }, h("label", { for: id }, "Slot " + (i + 1)), select);
        });
        const list = h("ol", { class: "slots" }, slots);
        const selects = () => Array.from(list.querySelectorAll("select"));
        // A product can sit in one slot only: grey it out in the other dropdowns.
        const sync = () => {
          const taken = selects().map((s) => s.value).filter(Boolean);
          selects().forEach((s) => Array.from(s.options).forEach((o) => { o.disabled = Boolean(o.value) && o.value !== s.value && taken.includes(o.value); }));
        };
        list.addEventListener("change", sync);
        sync();
        const note = h("p", { class: "muted" }, category.picks.length
          ? category.picks.length + " of " + category.limit + " slots filled. Shown on the home page in this order."
          : "Nothing chosen yet, so the home page shows the " + Math.min(category.limit, category.products.length) + " newest products in this category.");
        const save = isAdmin ? h("button", { class: "btn", type: "button" }, "Save " + category.name.toLowerCase() + " picks") : null;
        if (save) save.addEventListener("click", () => busy(save, async () => {
          render(await api("/admin/home-picks/" + category.id + "/", { method: "PUT", body: { product_ids: selects().map((s) => Number(s.value)).filter(Boolean) } }));
          toast(category.name + " picks saved.");
        }));
        return h("section", {}, h("h2", {}, category.name), note, list, save);
      }));
    }
    api("/admin/home-picks/").then(render).catch((error) => host.replaceChildren(empty(error.message)));
  }
})();
