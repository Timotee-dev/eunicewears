(function () {
  "use strict";
  const { api, toast, bindForm } = window.EW;
  const $ = (selector) => document.querySelector(selector);
  const params = new URLSearchParams(window.location.search);

  function safeNext() {
    const next = params.get("next") || "/account/";
    return next.startsWith("/") && !next.startsWith("//") ? next : "/account/"; // no open redirects
  }

  bindForm($('[data-form="login"]'), async (data) => {
    try {
      await api("/auth/login/", { method: "POST", body: data });
      window.location.assign(safeNext());
    } catch (error) {
      const resend = $("[data-resend]");
      if (error.code === "email_not_verified" && resend) {
        resend.querySelector('[name="email"]').value = data.email;
        resend.hidden = false;
      }
      throw error;
    }
  });

  bindForm($('[data-form="register"]'), async (data, form) => {
    await api("/auth/register/", { method: "POST", body: data });
    form.hidden = true;
    $("[data-success-email]").textContent = data.email;
    $("[data-success]").hidden = false;
  });

  document.querySelectorAll('[data-form="resend"]').forEach((form) =>
    bindForm(form, async (data) => {
      const result = await api("/auth/resend-verification/", { method: "POST", body: { email: data.email } });
      toast(result.message);
    })
  );

  bindForm($('[data-form="forgot"]'), async (data, form) => {
    await api("/auth/password/reset/", { method: "POST", body: data });
    form.hidden = true;
    $("[data-success]").hidden = false;
  });

  bindForm($('[data-form="reset"]'), async (data, form) => {
    await api("/auth/password/reset/confirm/", {
      method: "POST",
      body: { uid: params.get("uid") || "", token: params.get("token") || "", new_password: data.new_password },
    });
    form.hidden = true;
    $("[data-success]").hidden = false;
  });

  const verify = $("[data-verify]");
  if (verify) {
    const status = $("[data-verify-status]");
    api("/auth/verify-email/", { method: "POST", body: { uid: params.get("uid") || "", token: params.get("token") || "" } })
      .then((result) => { status.textContent = result.message; $("[data-verify-ok]").hidden = false; })
      .catch((error) => { status.textContent = error.message; $("[data-verify-fail]").hidden = false; });
  }
})();
