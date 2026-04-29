(function () {
  function setShellState(isAuthenticated) {
    document.body.classList.toggle('app-authenticated', !!isAuthenticated);
  }

  function bindAuthButtons() {
    document.querySelectorAll('[data-auth-target]').forEach(function (button) {
      if (button.dataset.boundAuth === '1') return;
      button.dataset.boundAuth = '1';
      button.addEventListener('click', function (event) {
        event.preventDefault();
        var mode = button.getAttribute('data-auth-target') || 'register';
        window.dispatchEvent(new CustomEvent('roofdraft:auth-open', { detail: { mode: mode } }));
      });
    });
  }

  function bindFaqItems() {
    document.querySelectorAll('.static-faq-question').forEach(function (button) {
      if (button.dataset.boundFaq === '1') return;
      button.dataset.boundFaq = '1';
      button.addEventListener('click', function () {
        var item = button.closest('.static-faq-item');
        if (!item) return;
        var isOpen = item.classList.contains('open');
        document.querySelectorAll('.static-faq-item.open').forEach(function (openItem) {
          if (openItem !== item) openItem.classList.remove('open');
        });
        item.classList.toggle('open', !isOpen);
        button.setAttribute('aria-expanded', String(!isOpen));
      });
    });
  }

  function bindContactForm() {
    var form = document.getElementById('marketing-contact-form');
    if (!form || form.dataset.boundForm === '1') return;
    form.dataset.boundForm = '1';

    var success = document.getElementById('marketing-contact-success');
    var error = document.getElementById('marketing-contact-error');
    var submit = document.getElementById('marketing-contact-submit');

    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      if (success) success.hidden = true;
      if (error) error.hidden = true;
      if (submit) {
        submit.disabled = true;
        submit.textContent = 'Sending...';
      }

      var payload = {
        name: form.elements.name ? form.elements.name.value : '',
        email: form.elements.email ? form.elements.email.value : '',
        message: form.elements.message ? form.elements.message.value : ''
      };

      try {
        var response = await fetch('/api/contact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error('Contact request failed');
        form.reset();
        if (success) success.hidden = false;
      } catch (err) {
        if (error) error.hidden = false;
      } finally {
        if (submit) {
          submit.disabled = false;
          submit.textContent = 'Send Message';
        }
      }
    });
  }

  function initMarketing() {
    bindAuthButtons();
    bindFaqItems();
    bindContactForm();
  }

  window.RoofDraftMarketing = {
    showShell: function () { setShellState(false); },
    hideShell: function () { setShellState(true); },
    init: initMarketing
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMarketing);
  } else {
    initMarketing();
  }
})();
