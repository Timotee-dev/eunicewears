(function () {
  "use strict";
  const { api, toast, bindForm } = window.EW;
  const $ = (selector) => document.querySelector(selector);
  const list = $("[data-addresses]");

  function line(text, className) {
    const p = document.createElement("p");
    p.textContent = text; // textContent only: customer input is never parsed as HTML
    if (className) p.className = className;
    return p;
  }

  function action(label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn--ghost btn--small";
    button.textContent = label;
    button.addEventListener("click", async () => {
      button.disabled = true;
      try { await handler(); await loadAddresses(); }
      catch (error) { button.disabled = false; toast(error.message, "error"); }
    });
    return button;
  }

  function render(addresses) {
    list.replaceChildren();
    list.setAttribute("aria-busy", "false");
    if (!addresses.length) {
      const empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "No addresses yet. Add one below so checkout is quicker.";
      list.appendChild(empty);
      return;
    }
    addresses.forEach((a) => {
      const item = document.createElement("li");
      item.className = "address" + (a.is_default ? " is-default" : "");
      if (a.is_default) { const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = "Default"; item.appendChild(badge); }
      item.appendChild(line(a.first_name + " " + a.last_name));
      item.appendChild(line([a.line1, a.line2].filter(Boolean).join(", ")));
      item.appendChild(line(a.city + ", " + a.state));
      item.appendChild(line(a.phone, "muted"));
      const actions = document.createElement("div");
      actions.className = "actions";
      if (!a.is_default) actions.appendChild(action("Make default", () => api("/account/addresses/" + a.id + "/", { method: "PATCH", body: { is_default: true } })));
      actions.appendChild(action("Remove", () => api("/account/addresses/" + a.id + "/", { method: "DELETE" })));
      item.appendChild(actions);
      list.appendChild(item);
    });
  }

  async function loadAddresses() {
    try { render(await api("/account/addresses/")); }
    catch (error) {
      list.replaceChildren();
      const failed = document.createElement("li");
      failed.className = "empty";
      failed.textContent = "Addresses did not load. Refresh the page to try again.";
      list.appendChild(failed);
    }
  }

  bindForm($('[data-form="profile"]'), async (data) => {
    await api("/auth/me/", { method: "PATCH", body: data });
    toast("Profile saved.");
  });

  bindForm($('[data-form="password"]'), async (data, form) => {
    await api("/auth/password/change/", { method: "POST", body: data });
    form.reset();
    toast("Password changed.");
  });

  bindForm($('[data-form="address"]'), async (data, form) => {
    await api("/account/addresses/", { method: "POST", body: data });
    ["line1", "line2", "city", "state", "delivery_instructions"].forEach((n) => (form.querySelector('[name="' + n + '"]').value = ""));
    form.closest("details").open = false;
    toast("Address saved.");
    await loadAddresses();
  });

  if (list) loadAddresses();

  const orders = $("[data-orders]");
  if (orders) {
    const { h, money, date } = window.EW;
    api("/orders/").then((page) => {
      orders.setAttribute("aria-busy", "false");
      if (!page.results.length) {
        orders.replaceChildren(h("p", { class: "empty" }, "No orders yet. ", h("a", { href: "/shop/" }, "Browse the shop")));
        return;
      }
      orders.replaceChildren(h("ul", { class: "order-list" }, page.results.map((o) =>
        h("li", {}, h("a", { href: "/account/orders/" + o.number + "/" },
          h("strong", {}, o.number), h("span", {}, date(o.created_at)),
          h("span", { class: "badge badge--" + o.status }, o.status_label), h("span", {}, money(o.total)))))));
    }).catch(() => orders.replaceChildren(h("p", { class: "empty" }, "Orders did not load. Refresh the page to try again.")));
  }
})();
