/* Axcess public site — progressive enhancement only.
   Everything on these pages works without JavaScript; this file adds
   a mobile menu toggle and the coverage-explorer filters. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.remove("no-js");
  root.classList.add("js");

  /* ---- Mobile navigation ---- */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    var mq = window.matchMedia("(max-width: 880px)");
    function sync() {
      if (mq.matches) {
        nav.hidden = toggle.getAttribute("aria-expanded") !== "true";
      } else {
        nav.hidden = false;
      }
    }
    toggle.addEventListener("click", function () {
      var open = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", open ? "false" : "true");
      sync();
    });
    if (mq.addEventListener) { mq.addEventListener("change", sync); } else { mq.addListener(sync); }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        toggle.setAttribute("aria-expanded", "false");
        sync();
        toggle.focus();
      }
    });
    sync();
  }

  /* ---- Coverage explorer ---- */
  var explorer = document.getElementById("explorer");
  if (!explorer) { return; }
  var cards = Array.prototype.slice.call(explorer.querySelectorAll(".crit"));
  var groups = Array.prototype.slice.call(explorer.querySelectorAll(".principle"));
  var count = document.getElementById("result-count");
  var search = document.getElementById("crit-search");
  var state = { method: "all", level: "all", q: "" };

  function apply() {
    var shown = 0;
    var q = state.q.trim().toLowerCase();
    cards.forEach(function (card) {
      var ok = true;
      if (state.method !== "all" && card.getAttribute("data-method") !== state.method) { ok = false; }
      if (ok && state.level !== "all" && card.getAttribute("data-level") !== state.level) { ok = false; }
      if (ok && q && card.getAttribute("data-text").indexOf(q) === -1) { ok = false; }
      card.hidden = !ok;
      if (ok) { shown += 1; }
    });
    groups.forEach(function (g) {
      var visible = g.querySelectorAll(".crit:not([hidden])").length;
      g.hidden = visible === 0;
      var n = g.querySelector("[data-visible]");
      if (n) { n.textContent = visible; }
    });
    if (count) {
      count.textContent = shown === cards.length
        ? "Showing all " + cards.length + " success criteria"
        : "Showing " + shown + " of " + cards.length + " success criteria";
    }
    if (q) {
      cards.forEach(function (card) { if (!card.hidden) { card.open = true; } });
    }
  }

  explorer.querySelectorAll("[data-filter]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var key = btn.getAttribute("data-filter");
      var val = btn.getAttribute("data-value");
      state[key] = val;
      explorer.querySelectorAll('[data-filter="' + key + '"]').forEach(function (b) {
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
      apply();
    });
  });
  if (search) {
    var t;
    search.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () { state.q = search.value; apply(); }, 120);
    });
  }
  var expandAll = document.getElementById("expand-all");
  var collapseAll = document.getElementById("collapse-all");
  if (expandAll) { expandAll.addEventListener("click", function () { cards.forEach(function (c) { if (!c.hidden) { c.open = true; } }); }); }
  if (collapseAll) { collapseAll.addEventListener("click", function () { cards.forEach(function (c) { c.open = false; }); }); }

  /* Deep link: /coverage/#sc-2-4-4 opens that criterion. */
  function openHash() {
    if (!location.hash) { return; }
    var el = document.getElementById(location.hash.slice(1));
    if (el && el.classList.contains("crit")) { el.open = true; el.hidden = false; }
  }
  window.addEventListener("hashchange", openHash);
  openHash();
  apply();
})();
