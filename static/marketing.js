(function () {
  function setShellState(isAuthenticated) {
    document.body.classList.toggle("app-authenticated", !!isAuthenticated);
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

  function bindScrollButtons() {
    document.querySelectorAll("[data-pro-access-target]").forEach(function (button) {
      if (button.dataset.boundScroll === "1") return;
      button.dataset.boundScroll = "1";
      button.addEventListener("click", function () {
        var targetId = button.getAttribute("data-pro-access-target");
        var target = targetId ? document.getElementById(targetId) : null;
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
          var nameInput = target.querySelector("input[name='name']");
          if (nameInput) {
            window.setTimeout(function () { nameInput.focus(); }, 350);
          }
        }
      });
    });
  }

  function buildProAccessMessage(form) {
    var company = form.elements.company ? form.elements.company.value.trim() : "";
    var phone = form.elements.phone ? form.elements.phone.value.trim() : "";
    var message = form.elements.message ? form.elements.message.value.trim() : "";
    var lines = ["[PRO ACCESS REQUEST]"];
    if (company) lines.push("Company: " + company);
    if (phone) lines.push("Phone: " + phone);
    lines.push("Requested from public pricing section before Stripe launch.");
    if (message) lines.push("", message);
    return lines.join("\n");
  }

  function bindProAccessForm() {
    var form = document.getElementById("pro-access-form");
    if (!form || form.dataset.boundForm === "1") return;
    form.dataset.boundForm = "1";

    var success = document.getElementById("pro-access-success");
    var error = document.getElementById("pro-access-error");
    var submit = document.getElementById("pro-access-submit");

    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (success) success.hidden = true;
      if (error) error.hidden = true;
      if (submit) {
        submit.disabled = true;
        submit.textContent = "Sending...";
      }

      var payload = {
        name: form.elements.name ? form.elements.name.value.trim() : "",
        email: form.elements.email ? form.elements.email.value.trim() : "",
        message: buildProAccessMessage(form)
      };

      try {
        var response = await fetch("/api/contact", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error("Pro access request failed");
        form.reset();
        if (success) success.hidden = false;
      } catch (err) {
        if (error) error.hidden = false;
      } finally {
        if (submit) {
          submit.disabled = false;
          submit.textContent = "Request Pro Access";
        }
      }
    });
  }

  function initMarketing() {
    bindAuthButtons();
    bindFaqItems();
    bindMobileMenu();
    bindScrollButtons();
    bindProAccessForm();
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
