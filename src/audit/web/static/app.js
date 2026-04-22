// Keyboard shortcuts for the findings list.
//   j / k : next / previous row
//   Enter : open focused row
//   /     : focus the filter input
//   s     : focus the status dropdown on the current row / finding page
// All shortcuts are scoped: they're suppressed while a text input is focused.

(function () {
  "use strict";

  function isEditing(el) {
    if (!el) return false;
    const tag = (el.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function rows() {
    return Array.from(document.querySelectorAll("tr[data-finding-id]"));
  }

  function currentIndex(all) {
    const active = document.querySelector('tr[data-finding-id][aria-current="true"]');
    if (!active) return -1;
    return all.indexOf(active);
  }

  function select(idx) {
    const all = rows();
    if (!all.length) return;
    all.forEach((r) => r.removeAttribute("aria-current"));
    const clamped = Math.max(0, Math.min(idx, all.length - 1));
    const target = all[clamped];
    target.setAttribute("aria-current", "true");
    target.scrollIntoView({ block: "nearest" });
    // Move focus to the first link in the row so Enter / Tab work naturally.
    const link = target.querySelector("a");
    if (link) link.focus();
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    if (isEditing(ev.target)) return;

    const all = rows();
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
        const select = document.querySelector("select[data-status-select]");
        if (select) {
          ev.preventDefault();
          select.focus();
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
