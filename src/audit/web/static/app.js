// Keyboard shortcuts — scoped, suppressed while typing in a form field.
//
// Findings list:
//   j / k     — next / previous card
//   Enter     — open focused card
//   /         — focus the filter input
//
// Finding detail:
//   0–5       — set status (new, reviewing, in_progress, remediated,
//                accepted_risk, false_positive) and submit
//   s         — focus the status dropdown
//
// Anywhere:
//   ?         — toggle the keyboard-help panel

(function () {
  "use strict";

  const STATUS_KEYS = {
    "0": "new",
    "1": "reviewing",
    "2": "in_progress",
    "3": "remediated",
    "4": "accepted_risk",
    "5": "false_positive",
  };

  function isEditing(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    return !!el.isContentEditable;
  }

  function cards() {
    return Array.from(document.querySelectorAll("[data-finding-id]"));
  }

  function currentIndex(all) {
    const active = document.querySelector('[data-finding-id][aria-current="true"]');
    if (!active) return -1;
    return all.indexOf(active);
  }

  function select(idx) {
    const all = cards();
    if (!all.length) return;
    all.forEach((r) => r.removeAttribute("aria-current"));
    const clamped = Math.max(0, Math.min(idx, all.length - 1));
    const target = all[clamped];
    target.setAttribute("aria-current", "true");
    target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const link = target.querySelector("a");
    if (link) link.focus();
  }

  function submitStatus(value) {
    const sel = document.querySelector("select[data-status-select]");
    if (!sel) return false;
    const form = sel.closest("form");
    if (!form) return false;
    sel.value = value;
    const changed = new Event("change", { bubbles: true });
    sel.dispatchEvent(changed);
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
    return true;
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (isEditing(ev.target)) return;

    if (Object.prototype.hasOwnProperty.call(STATUS_KEYS, ev.key)) {
      if (submitStatus(STATUS_KEYS[ev.key])) {
        ev.preventDefault();
      }
      return;
    }

    const all = cards();
    switch (ev.key) {
      case "j": {
        if (!all.length) return;
        ev.preventDefault();
        const cur = currentIndex(all);
        select(cur < 0 ? 0 : cur + 1);
        break;
      }
      case "k": {
        if (!all.length) return;
        ev.preventDefault();
        const cur = currentIndex(all);
        select(cur < 0 ? 0 : cur - 1);
        break;
      }
      case "/": {
        const input = document.querySelector("input[data-filter-focus]");
        if (input) {
          ev.preventDefault();
          input.focus();
          input.select();
        }
        break;
      }
      case "s": {
        const sel = document.querySelector("select[data-status-select]");
        if (sel) {
          ev.preventDefault();
          sel.focus();
        }
        break;
      }
      case "?": {
        const help = document.getElementById("kb-help");
        if (help) {
          ev.preventDefault();
          help.hidden = !help.hidden;
          if (!help.hidden) help.focus();
        }
        break;
      }
    }
  });
})();
