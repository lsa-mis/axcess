// Shared behaviour for the modal verification fixtures.
//
// Each page sets <body data-variant="..."> and gets one modal dialog with a
// trigger button. The variant switches off exactly one piece of correct
// modal behaviour, so a probe result can be tied to one cause:
//
//   good       focus moves in, Tab stays inside, Escape closes, focus returns
//   no-trap    Tab walks out of the open dialog into the page behind it
//   no-escape  Escape does nothing; the Close button still works
//   no-return  closing leaves focus on the page body, not on the trigger
//   no-exit    no Escape, and the only button is "Got it" (not a close word)
//   hard-trap  the dialog's only control swallows Tab and Shift+Tab and
//              there is no Escape and no button: a real SC 2.1.2 trap
(function () {
  const variant = document.body.dataset.variant;
  const trigger = document.getElementById('trigger');
  const dialog = document.getElementById('dialog');
  const veil = document.getElementById('veil');
  const behind = document.getElementById('behind');

  const focusables = () =>
    Array.from(dialog.querySelectorAll('button, input, a[href]'));

  function open() {
    dialog.hidden = false;
    veil.hidden = false;
    // The page behind a correct modal is inert. no-trap leaves it live, so
    // Tab can reach it.
    if (variant !== 'no-trap') behind.inert = true;
    const first = focusables()[0];
    if (first) first.focus();
  }

  function close() {
    dialog.hidden = true;
    veil.hidden = true;
    behind.inert = false;
    if (variant === 'no-return') {
      document.activeElement && document.activeElement.blur();
    } else {
      trigger.focus();
    }
  }

  trigger.addEventListener('click', open);
  const closeBtn = document.getElementById('close');
  if (closeBtn) closeBtn.addEventListener('click', close);

  dialog.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (variant === 'no-escape' || variant === 'no-exit' || variant === 'hard-trap') return;
      e.preventDefault();
      close();
      return;
    }
    if (e.key !== 'Tab') return;
    if (variant === 'hard-trap') {
      e.preventDefault();
      return;
    }
    if (variant === 'no-trap') return;
    // Wrap focus inside the dialog (WAI-ARIA APG modal dialog pattern).
    const items = focusables();
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  });

  // ?open=1 opens the dialog as the page loads, so a load-state probe can
  // see it open.
  if (new URLSearchParams(location.search).get('open') === '1') open();
})();
