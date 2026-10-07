/* Eunice Wears client core: API wrapper, toasts, form handling, header.
   The browser never decides prices, stock, or permissions; it only asks the API. */
(function () {
  "use strict";

  function cookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  class ApiError extends Error {
    constructor(status, payload) {
      const err = (payload && payload.error) || {};
      super(err.message || "Something went wrong. Try again.");
      this.status = status;
      this.code = err.code || "error";
      this.fields = err.fields || null;
    }
  }

  async function api(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = { Accept: "application/json" };
    const isForm = options.body instanceof FormData;
    if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
    if (method !== "GET") headers["X-CSRFToken"] = cookie("csrftoken");
    let response;
    try {
      response = await fetch("/api" + path, {
        method,
        headers,
        credentials: "same-origin",
        body: options.body === undefined ? undefined : isForm ? options.body : JSON.stringify(options.body),
      });
    } catch (e) {
      throw new ApiError(0, { error: { code: "network", message: "No connection. Check your internet and try again." } });
    }
    if (response.status === 204) return null;
    let payload = null;
    try { payload = await response.json(); } catch (e) { /* non-JSON error page */ }
    if (!response.ok) {
      if (response.status === 429) payload = { error: { code: "throttled", message: "Too many attempts. Wait a minute and try again." } };
      throw new ApiError(response.status, payload);
    }
    return payload;
  }

  /* Build DOM nodes without innerHTML: strings become text nodes, so data can never inject markup. */
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value === null || value === undefined || value === false) return;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
      else if (key in el && key !== "list" && key !== "form") el[key] = value;
      else el.setAttribute(key, value === true ? "" : value);
    });
    children.flat().forEach((child) => { if (child !== null && child !== undefined && child !== false) el.append(child); });
    return el;
  }

  function money(kobo) {
    const naira = Number(kobo || 0) / 100;
    return "\u20a6" + naira.toLocaleString("en-NG", { minimumFractionDigits: naira % 1 ? 2 : 0, maximumFractionDigits: 2 });
  }

  function date(iso) {
    return new Date(iso).toLocaleString("en-NG", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function setCartCount(count) {
    document.querySelectorAll("[data-cart-count]").forEach((el) => {
      el.textContent = count;
      el.classList.remove("is-bump");
      void el.offsetWidth; // restart the animation
      el.classList.add("is-bump");
    });
  }

  /* Run an async action from a button: disable while busy, toast any API error. */
  async function busy(button, action) {
    button.disabled = true;
    try { return await action(); }
    catch (error) { if (error instanceof ApiError) toast(error.message, "error"); else throw error; }
    finally { button.disabled = false; }
  }

  function toast(message, type) {
    const host = document.querySelector("[data-toasts]");
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast" + (type === "error" ? " toast--error" : "");
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => { el.classList.add("is-leaving"); setTimeout(() => el.remove(), 320); }, 4700);
  }

  function formData(form) {
    const data = {};
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach((el) => {
      data[el.name] = el.type === "checkbox" ? el.checked : el.value;
    });
    return data;
  }

  function clearErrors(form) {
    form.querySelectorAll("[data-error-for]").forEach((el) => (el.textContent = ""));
    form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
    const box = form.querySelector("[data-form-error]");
    if (box) box.hidden = true;
  }

  function showErrors(form, error) {
    let placed = false;
    Object.entries(error.fields || {}).forEach(([name, messages]) => {
      const slot = form.querySelector('[data-error-for="' + name + '"]');
      const input = form.querySelector('[name="' + name + '"]');
      if (slot) {
        slot.textContent = messages.join(" ");
        placed = true;
        if (input) {
          input.setAttribute("aria-invalid", "true");
          if (!slot.id) slot.id = "err-" + name + "-" + Math.random().toString(36).slice(2, 7);
          input.setAttribute("aria-describedby", slot.id);
        }
      }
    });
    const first = form.querySelector('[aria-invalid="true"]');
    if (first) first.focus();
    const box = form.querySelector("[data-form-error]");
    if (!placed || !error.fields) {
      if (box) { box.textContent = error.message; box.hidden = false; } else { toast(error.message, "error"); }
    }
  }

  /* Wire a form: disables the button while busy, renders API errors next to fields. */
  function bindForm(form, handler) {
    if (!form) return;
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      const label = button ? button.textContent : "";
      clearErrors(form);
      if (button) { button.disabled = true; button.textContent = (button.dataset.busyLabel || "Working") + "\u2026"; }
      try {
        await handler(formData(form), form);
      } catch (error) {
        if (error instanceof ApiError) showErrors(form, error); else throw error;
      } finally {
        if (button) { button.disabled = false; button.textContent = label; }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector("[data-menu-toggle]");
    const nav = document.getElementById("site-nav");
    if (toggle && nav) {
      toggle.addEventListener("click", () => {
        const open = nav.classList.toggle("is-open");
        toggle.setAttribute("aria-expanded", String(open));
      });
    }
    const logout = document.querySelector("[data-logout]");
    if (logout) {
      logout.addEventListener("click", async () => {
        logout.disabled = true;
        try { await api("/auth/logout/", { method: "POST" }); window.location.assign("/"); }
        catch (error) { logout.disabled = false; toast(error.message, "error"); }
      });
    }
  });

  /* Slide-in cart panel shown after "Add to cart". */
  function openCartDrawer(cart) {
    const drawer = document.querySelector("[data-cart-drawer]");
    if (!drawer || !drawer.showModal) { toast("Added to cart."); return; }
    drawer.querySelector("[data-drawer-lines]").replaceChildren(...cart.items.map((item) => h("li", { class: "drawer__line" },
      item.image ? h("img", { src: item.image, alt: "", width: 64, height: 80 }) : h("div", { class: "card__blank drawer__blank", "aria-hidden": "true" }, "EW"),
      h("div", {}, h("strong", {}, item.product), h("p", { class: "muted small" }, item.label + " \u00d7 " + item.quantity)),
      h("span", { class: "drawer__price" }, money(item.line_total)))));
    drawer.querySelector("[data-drawer-subtotal]").textContent = money(cart.subtotal);
    if (!drawer.open) drawer.showModal();
  }

  /* The delivery-address form, used on the account page and at checkout. It adds a new address,
     or edits an existing one after edit(address) is called. */
  function addressForm(form, onSaved) {
    if (!form) return { edit() {} };
    const FIELDS = ["first_name", "last_name", "phone", "line1", "line2", "city", "state", "delivery_instructions"];
    const details = form.closest("details"), summary = details ? details.querySelector("summary") : null;
    const button = form.querySelector('[type="submit"]');
    const addSummary = summary ? summary.textContent : "", addButton = button.textContent;
    let editing = null;
    const paint = () => { button.textContent = editing ? "Save changes" : addButton; if (summary) summary.textContent = editing ? "Edit this address" : addSummary; };
    const clear = () => { editing = null; ["line1", "line2", "city", "state", "delivery_instructions"].forEach((n) => { form.elements[n].value = ""; }); paint(); };
    bindForm(form, async (data) => {
      const body = {};
      FIELDS.forEach((n) => { body[n] = data[n]; });
      const wasEditing = Boolean(editing);
      const saved = await api("/account/addresses/" + (editing ? editing + "/" : ""), { method: editing ? "PATCH" : "POST", body });
      clear();
      if (details) details.open = false;
      toast(wasEditing ? "Address updated." : "Address saved.");
      await onSaved(saved);
    });
    if (details) details.addEventListener("toggle", () => { if (!details.open && editing) clear(); else paint(); });
    return {
      edit(address) {
        editing = address.id;
        FIELDS.forEach((n) => { form.elements[n].value = address[n] || ""; });
        if (details) details.open = true;
        paint();
        form.scrollIntoView({ behavior: "smooth", block: "center" });
        form.elements.line1.focus({ preventScroll: true });
      },
    };
  }

  window.EW = { api, ApiError, toast, bindForm, h, money, date, setCartCount, busy, openCartDrawer, addressForm };
})();

/* Site-wide extras: newsletter signup and search suggestions in the header. */
(function () {
  "use strict";
  const { api, toast, bindForm, h, money } = window.EW;

  bindForm(document.querySelector('[data-form="newsletter"]'), async (data, form) => {
    const result = await api("/newsletter/", { method: "POST", body: { email: data.email } });
    form.reset();
    toast(result.message);
  });

  const search = document.querySelector("[data-search]");
  if (search) {
    const input = search.elements.q, list = search.querySelector("[data-suggestions]");
    let timer = null, latest = 0;
    const close = () => { list.hidden = true; list.replaceChildren(); };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) { close(); return; }
      timer = setTimeout(async () => {
        const ticket = ++latest;
        try {
          const results = await api("/products/suggest/?q=" + encodeURIComponent(q));
          if (ticket !== latest) return; // a newer keystroke already answered
          list.replaceChildren(...(results.length
            ? results.map((p) => h("li", {}, h("a", { href: "/product/" + p.slug + "/" }, h("span", {}, p.name), h("span", { class: "muted" }, money(p.price)))))
            : [h("li", {}, h("a", { href: "/shop/?q=" + encodeURIComponent(q) }, "No quick matches. Search the whole shop"))]));
          list.hidden = false;
        } catch (error) { close(); }
      }, 250);
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
    document.addEventListener("click", (e) => { if (!search.contains(e.target)) close(); });
  }
})();

/* Motion and chrome: scroll reveals, header state, cart drawer controls. All of it is progressive:
   with JavaScript off or reduced motion on, content is simply visible. */
(function () {
  "use strict";
  const root = document.documentElement;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (!calm && "IntersectionObserver" in window) {
    root.classList.add("has-motion");
    const seen = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add("is-in"); seen.unobserve(entry.target); }
    }), { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    document.querySelectorAll("[data-reveal]").forEach((el, i) => {
      el.style.transitionDelay = (i % 3) * 90 + "ms";
      seen.observe(el);
    });
  }

  const header = document.querySelector("[data-header]");
  if (header) {
    const mark = () => header.classList.toggle("is-scrolled", window.scrollY > 12);
    window.addEventListener("scroll", mark, { passive: true });
    mark();
  }

  // Highlight the current section link.
  document.querySelectorAll(".subnav a").forEach((link) => {
    if (link.getAttribute("href") === window.location.pathname + window.location.search) link.setAttribute("aria-current", "page");
  });

  const drawer = document.querySelector("[data-cart-drawer]");
  if (drawer) {
    drawer.querySelector("[data-drawer-close]").addEventListener("click", () => drawer.close());
    drawer.addEventListener("click", (event) => { if (event.target === drawer) drawer.close(); });
  }
})();
