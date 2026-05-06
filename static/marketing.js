(function () {
  function clearAuthBootState() {
    document.documentElement.classList.remove("roofdraft-dashboard-pending");
    if (document.body) {
      document.body.classList.remove("app-auth-pending");
    }
  }

  function setHiddenByState(selector, hidden) {
    document.querySelectorAll(selector).forEach(function (element) {
      element.hidden = !!hidden;
    });
  }

  function syncFooterAuthLinks(isAuthenticated) {
    setHiddenByState('[data-footer-auth-state="guest"]', !!isAuthenticated);
    setHiddenByState('[data-footer-auth-state="auth"]', !isAuthenticated);
  }

  function setShellState(isAuthenticated) {
    clearAuthBootState();
    document.body.classList.toggle("app-authenticated", !!isAuthenticated);
    setHiddenByState("[data-marketing-shell-sibling]", !!isAuthenticated);
    syncFooterAuthLinks(!!isAuthenticated);
  }

  function bindAuthButtons() {
    document.querySelectorAll("[data-auth-target]").forEach(function (button) {
      if (button.dataset.boundAuth === "1") return;
      button.dataset.boundAuth = "1";
      button.addEventListener("click", function (event) {
        event.preventDefault();
        var mode = button.getAttribute("data-auth-target") || "register";
        window.dispatchEvent(new CustomEvent("roofdraft:auth-open", { detail: { mode: mode } }));
      });
    });
  }

  function bindUpgradeButtons() {
    document.querySelectorAll("[data-upgrade-plan]").forEach(function (button) {
      if (button.dataset.boundUpgrade === "1") return;
      button.dataset.boundUpgrade = "1";
      button.addEventListener("click", function (event) {
        event.preventDefault();
        var plan = button.getAttribute("data-upgrade-plan") || "pro";
        window.dispatchEvent(new CustomEvent("roofdraft:upgrade-request", { detail: { plan: plan } }));
      });
    });
  }

  function bindFaqItems() {
    document.querySelectorAll(".static-faq-question").forEach(function (button) {
      if (button.dataset.boundFaq === "1") return;
      button.dataset.boundFaq = "1";
      button.addEventListener("click", function () {
        var item = button.closest(".static-faq-item");
        if (!item) return;
        var isOpen = item.classList.contains("open");
        document.querySelectorAll(".static-faq-item.open").forEach(function (openItem) {
          if (openItem !== item) openItem.classList.remove("open");
        });
        item.classList.toggle("open", !isOpen);
        button.setAttribute("aria-expanded", String(!isOpen));
      });
    });
  }

  function bindContactForm() {
    var form = document.querySelector("[data-contact-form]");
    if (!form || form.dataset.boundContact === "1") return;
    form.dataset.boundContact = "1";

    var successBox = document.querySelector("[data-contact-success]");
    var errorBox = document.querySelector("[data-contact-error]");
    var submitButton = document.querySelector("[data-contact-submit]");
    var submitText = document.querySelector("[data-contact-submit-text]");

    function setState(isLoading) {
      if (submitButton) submitButton.disabled = !!isLoading;
      if (submitText) submitText.textContent = isLoading ? "Sending..." : "Send Message";
      if (submitButton) submitButton.setAttribute("aria-busy", isLoading ? "true" : "false");
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;

      var payload = {
        name: (form.elements.name && form.elements.name.value || "").trim(),
        email: (form.elements.email && form.elements.email.value || "").trim(),
        message: (form.elements.message && form.elements.message.value || "").trim()
      };

      if (successBox) successBox.hidden = true;
      if (errorBox) errorBox.hidden = true;
      setState(true);

      fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          return { ok: response.ok, data: data };
        });
      }).then(function (result) {
        if (result.ok) {
          form.reset();
          if (successBox) successBox.hidden = false;
          if (errorBox) errorBox.hidden = true;
        } else {
          if (successBox) successBox.hidden = true;
          if (errorBox) errorBox.hidden = false;
        }
      }).catch(function () {
        if (successBox) successBox.hidden = true;
        if (errorBox) errorBox.hidden = false;
      }).finally(function () {
        setState(false);
      });
    });
  }

  function bindMobileMenu() {
    var toggle = document.querySelector(".marketing-mobile-toggle");
    var panel = document.querySelector(".marketing-mobile-panel");
    if (!toggle || !panel || toggle.dataset.boundMenu === "1") return;
    toggle.dataset.boundMenu = "1";

    function closeMenu() {
      panel.classList.remove("open");
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }

    toggle.addEventListener("click", function () {
      var nextOpen = !panel.classList.contains("open");
      panel.classList.toggle("open", nextOpen);
      panel.hidden = !nextOpen;
      toggle.setAttribute("aria-expanded", String(nextOpen));
    });

    panel.querySelectorAll("a, button").forEach(function (item) {
      item.addEventListener("click", closeMenu);
    });

    document.addEventListener("click", function (event) {
      if (!panel.classList.contains("open")) return;
      if (panel.contains(event.target) || toggle.contains(event.target)) return;
      closeMenu();
    });
  }

  function initMarketing() {
    bindAuthButtons();
    bindUpgradeButtons();
    bindFaqItems();
    bindMobileMenu();
    bindContactForm();
    syncFooterAuthLinks(document.body.classList.contains("app-authenticated"));
  }

  window.RoofDraftMarketing = {
    showShell: function () { setShellState(false); },
    hideShell: function () { setShellState(true); },
    init: initMarketing
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMarketing);
  } else {
    initMarketing();
  }
})();
