# Scanning search-driven applications

A page can be a search interface with no links until a query is entered.
Rendering its initial DOM does not enumerate its result routes.

**Click through menus, tabs and dialogs** is on by default for new scans on
both the **Public website** and **Site with a login or 2FA** tabs. It explores
controls and queues additional routes they reveal. You can turn it off under
Advanced settings, in the **Coverage** group.

Automatic exploration attempts up to 100 controls per page, 20 of each
repeated structural shape, and five nested levels, with a two-minute limit.
Equal labels and shared CSS classes do not make distinct controls identical.
Focusable custom menu entries are explored even when their ARIA roles are
missing.

If choosing an entry closes a menu, the probe reopens the known ancestor
controls to reach remaining entries. Recreated menus are matched only when the
replacement control is unambiguous, and every reopen consumes the same
click/time budget. Ordinary focus targets and menu containers are not treated
as actions.

Exploration includes native checkboxes/radios, fixed-position controls, menu
items, tree items and placeholder-anchor disclosures. Ordinary links are
queued through the crawler's scope and page limits.

The probe skips disabled/hidden controls, form submissions, file inputs,
downloads, and controls named for subscription, payment, account changes,
sending, saving, deletion or other blocked actions. During exploration it
blocks HTTP writes, dismisses browser confirmation dialogs, and prevents
new-window/document navigation from bypassing the crawl frontier.

Same-origin read requests fall through to the existing scope and network
guards; cross-origin requests made during automatic clicks are blocked.
POST-based content loading can therefore remain unexplored. Service workers
are blocked in crawl-owned contexts; a supplied context with active workers is
not probed.

These checks are defense in depth, not a guarantee that arbitrary site code
is read-only: GET endpoints, pre-existing sockets, and unrecognizable custom
controls remain limitations. Use an authorized test account/site for sensitive
workflows. A page checked does not mean every control or state was exhausted;
limits, skipped actions and custom interactions still require manual review.

In **New scan**, open **Advanced settings**, then the **Checks** group, and
turn on **Search to discover result pages**. This works on both the **Public
website** and **Site with a login or 2FA** tabs. It needs axe-core and browser
rendering, so it is unavailable with **Fast crawl without a browser** or with
Siteimprove Alfa as the only rule engine.

1. Leave the search page URL blank to use the scan's starting page, or enter
   a page within the scan scope.
2. Add the input's accessible label (or a CSS selector) and a non-sensitive
   example value. Native selects support choosing an option by its label.
3. Enable **Press a search button** for submitted forms. Leave it off for
   live autocomplete.
4. Set the result selector to the links or options that open individual
   results, such as `.results a` or `[role=option]`.
5. If needed, turn on **Follow result pagination** and adjust **Maximum
   results** and **Maximum result pages**. Then tick the box that authorizes
   these search inputs and result clicks.

The runner checks each result-list state, captures routes from clicked
options even when they have no `href`, and replays the search after a result
opens.

Links revealed by ordinary DOM-state clicks also enter the crawl queue.
Normal scope, exclusions, depth and total-page limits still apply.
Signed-in searches use the same browser session as the rest of that scan.

The implementation uses browser DOM behavior, without framework detection.
The regression app in `tests/fixtures/vue-search/` runs real Vue and Vue
Router and has 51 reachable URLs. Its integration test verifies public,
signed-in history, and signed-in hash routing with tab-scoped session storage.
Additional browser tests cover submitted forms, delayed navigation, selects,
DOM-only results, empty results, and bounded exploration.

Search settings are stored locally in the scan configuration. Search outcome
counts are stored in `scan_search_runs`.

In the report's **What this scan actually checked** list, the
**Configured search** row distinguishes checked states from no results,
failed controls and limits. The **Click Through DOM States** row separately
reports ordinary click-probe coverage. A selected method alone is not evidence
that it completed work.

When a click opens a **modal** (`aria-modal="true"`, or a native `<dialog>`
opened with `showModal()`), the probe explores inside it, then closes it and
confirms it closed before touching the next control. It tries Escape first.
If that fails, it uses the dialog's own close control, but only when the name
clearly means dismiss, such as `Close`, `Cancel`, `Dismiss`, or `×`. It does
not count `OK`, `Done`, or `Continue` as a dismissal, because on a
confirmation dialog those perform the action.

A dialog that will not close **ends that page's exploration**: its overlay
covers every remaining control, so continuing would record clicks that only
landed on the overlay.

The page's ledger row stores `dialogs_stuck`, the
`dialog_not_dismissed` limit, and a reproduction note naming the dialog, the
control that opened it, and what dismissal was tried. Treat it as a lead for
manual review: Escape is a strong convention for dialogs, but it is not by
itself a WCAG requirement, so Axcess reports the observation rather than
asserting a conformance failure.

A `role="dialog"` that declares no modality blocks nothing and is treated as
an ordinary panel: halting on one would discard the rest of the page for no
reason. The consequence is that a dialog which *behaves* modally without
declaring it is not recognized as one here; that gap is itself a defect worth
fixing in the page.

Axcess stores per-page click coverage in `scan_interaction_runs`:

- the controls each page exposed, including ones a click revealed;
- how many distinct controls were operated;
- clicks dispatched;
- DOM states reached;
- controls refused by the blocked-label filter;
- which bound (clicks, time, depth, or repeated shapes) ended the sweep.

The report's **Click Through DOM States** row shows "N of M controls
operated". That way a reader can tell when most controls on a page were
refused or capped. Discovery is not coverage: a counted control was not
necessarily operated. Reports written before this ledger existed show the
page and state counts only, rather than a zero that would look like a
finding.

A configured search runs with the auditor's explicit authorization and is
**not** subject to the automatic-click HTTP write guard; only out-of-scope
main-frame navigation is blocked during a search journey.

Coverage depends on the chosen query, permissions, selectors and limits.
This does not promise every route in every SPA: other queries may reveal
additional results, custom widgets may need CSS selectors, and actions that
change records should never be configured as search/result controls.

The search runner caps a journey at two minutes, six fields, five result
pages and fifty discovered results. Returned routes can reveal further links
through the normal crawl, up to the scan's total-page limit.
