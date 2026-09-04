"""Integration tests for the live-page interaction probe.

Real Playwright + real axe against ``tests/fixtures/site/interaction/``.

The fixture is built so each guarantee fails loudly rather than silently:

  * an ``image-alt`` violation is present at load — it must be reported by
    the load-state pass and never again, however many revealed states it
    survives into;
  * an unlabelled input does not exist until "Add another guest" is pressed
    — a load-time-only scan cannot see it at all;
  * a "Sign out" button records its own activation, so the blocked-label
    guard is verified by observation rather than assumed;
  * ten same-shaped calendar buttons increment a counter, so the repeat cap
    is measured rather than assumed.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from audit.analyzer.axe import AxeAnalyzer
from audit.analyzer.interaction import InteractionProbe

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "site" / "interaction"


def _file_url(name: str) -> str:
    return (FIXTURE_DIR / name).resolve().as_uri()


playwright = pytest.importorskip("playwright.async_api")


@pytest.fixture
async def browser():  # type: ignore[no-untyped-def]
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            await browser.close()
    finally:
        await pw.stop()


@pytest.fixture
async def page(browser):  # type: ignore[no-untyped-def]
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = await ctx.new_page()
        yield p
    finally:
        await ctx.close()


@pytest.fixture
def axe() -> AxeAnalyzer:
    return AxeAnalyzer.from_bundled()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reveals_violation_that_only_exists_after_a_click(page, axe) -> None:  # type: ignore[no-untyped-def]
    """The unlabelled input appears only after "Add another guest"."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    # The whole premise: a load-time pass cannot see this.
    assert not any(v.rule_id == "label" for v in baseline)

    probe = InteractionProbe(axe=axe)
    revealed = (await probe.run(page, baseline=baseline)).findings

    label_findings = [r for r in revealed if r.violation.rule_id == "label"]
    assert label_findings, "probe did not find the input revealed by clicking"
    assert "Add another guest" in label_findings[0].revealed_by


@pytest.mark.integration
@pytest.mark.asyncio
async def test_load_state_violation_is_never_reported_again(page, axe) -> None:  # type: ignore[no-untyped-def]
    """The core dedupe guarantee.

    ``image-alt`` is on the page at load and survives into every state a
    click reveals. It must appear in the baseline and be entirely absent
    from the probe's output — otherwise it would be reported once per
    clicked state.
    """
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")
    assert any(v.rule_id == "image-alt" for v in baseline), "fixture regressed"

    revealed = (await InteractionProbe(axe=axe).run(page, baseline=baseline)).findings

    assert not any(r.violation.rule_id == "image-alt" for r in revealed)
    # Nothing is emitted twice, whatever the rule.
    hashes = [r.violation.target_hash for r in revealed]
    assert len(hashes) == len(set(hashes))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_never_operates_a_destructive_control(page, axe) -> None:  # type: ignore[no-untyped-def]
    """ "Sign out" must not be clicked, and the page proves it."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    await InteractionProbe(axe=axe).run(page, baseline=baseline)

    signed_out = await page.evaluate("() => document.body.dataset.signedOut || 'no'")
    assert signed_out == "no", "probe clicked a control whose label is blocked"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_repeated_controls_are_sampled_not_exhausted(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Ten same-shaped buttons must not produce ten clicks."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    await InteractionProbe(axe=axe, max_repeated=3).run(page, baseline=baseline)

    clicks = int(await page.evaluate("() => document.getElementById('clicks').textContent"))
    assert clicks <= 3, f"repeat cap ignored: {clicks} calendar buttons clicked"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_click_budget_is_respected(page, axe) -> None:  # type: ignore[no-untyped-def]
    """A tight budget bounds the work even on a page full of controls."""
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    revealed = (await InteractionProbe(axe=axe, max_clicks=2).run(page, baseline=baseline)).findings

    # The budget counts CLICKS, not findings: one revealed state can carry
    # several violations at once (an unlabelled input fails `label` and
    # `target-size` together). So bound the number of distinct controls
    # credited with a reveal, which is what the budget actually governs.
    controls_used = {r.revealed_by for r in revealed}
    assert len(controls_used) <= 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_control_is_operated_only_once(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Regression: the nested sweep must not re-click its own parent.

    ``_operate`` recurses into whatever the click revealed. That nested
    sweep re-reads the DOM, so if the control were only recorded as seen
    *after* ``_operate`` returned, the nested sweep would find it untouched
    and press it again — once per depth level. An end-to-end run caught this
    as one "Add another guest" press appending three inputs and reporting
    one defect three times over.

    The form holds one input per press, so it counts the presses directly.
    """
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    revealed = (await InteractionProbe(axe=axe, max_depth=2).run(page, baseline=baseline)).findings

    presses = await page.evaluate(
        "() => document.getElementById('guests').querySelectorAll('input').length"
    )
    assert presses == 1, f"control operated {presses} times, expected once"

    # ...and therefore the one unlabelled input is one finding, not three.
    assert len([r for r in revealed if r.violation.rule_id == "label"]) == 1


async def test_nested_control_is_explored_at_depth_one(page, axe) -> None:  # type: ignore[no-untyped-def]
    """A control revealed by a click must be reachable, and cost one level.

    The stress fixture holds a genuine two-level chain: "Account menu"
    reveals "More options", which reveals an unlabelled field. Reaching
    that field is only possible if the nested sweep looks at what the
    click revealed instead of re-reading the whole document — when it
    re-read the document, the first control that changed anything dragged
    every flat button on the page down to depth 1, and the depth budget
    was gone before the chain could be walked.
    """
    await page.goto(_file_url("stress.html"))
    baseline = await axe.run(page, "AA")

    revealed = (
        await InteractionProbe(axe=axe, max_clicks=40, max_depth=2).run(page, baseline=baseline)
    ).findings

    deep = [r for r in revealed if r.violation.target_selector == "#deep-field"]
    assert deep, (
        "the field behind Account menu -> More options was not reached; "
        "nested sweeps are not scoped to the revealed subtree"
    )
    assert deep[0].violation.rule_id == "label"
    # Attributed to the control actually operated, not to the outer menu.
    assert deep[0].revealed_by == "More options"


async def test_flat_controls_do_not_consume_recursion_depth(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Depth must measure nesting, not "how many clicks changed something".

    With ``max_depth=1`` no nested sweep may run at all. Every control that
    was operable at load must still be operated, because none of them are
    nested — they only looked nested when the sweep re-read the document.
    """
    await page.goto(_file_url("stress.html"))
    baseline = await axe.run(page, "AA")

    revealed = (
        await InteractionProbe(axe=axe, max_clicks=40, max_depth=1).run(page, baseline=baseline)
    ).findings

    # Reachable without descending: each is a top-level control.
    for label in ("Add another guest", "Photos", "Open booking dialog"):
        assert any(r.revealed_by == label for r in revealed), (
            f'"{label}" is a load-state control and must be operated at depth 0'
        )
    # Not reachable: it only exists after another click.
    assert not any(r.revealed_by == "More options" for r in revealed), (
        "max_depth=1 forbids descending, so the nested control must be skipped"
    )


@pytest.mark.parametrize("max_depth", [1, 2, 3, 4, 5])
async def test_depth_limit_counts_nesting_levels_exactly(page, axe, max_depth) -> None:  # type: ignore[no-untyped-def]
    """``max_depth=N`` must reach exactly N levels of a nesting chain.

    ``nested_depth.html`` is a five-level chain where each level reveals both
    an uniquely-numbered unlabelled field and the button for the next level,
    so the deepest field found is an exact readout of the recursion depth.

    This pins down two failures that both let depth drift from nesting. The
    sweep used to re-read the whole document on every pass, so a revealed
    button was picked back up at depth 0 and clicked there: the chain walked
    to level three under ``max_depth=1``. And the nested sweep used to see
    the whole document rather than what the click revealed, which spent the
    depth budget on flat controls before any chain could be walked.
    """
    await page.goto(_file_url("nested_depth.html"))
    baseline = await axe.run(page, "AA")

    revealed = (
        await InteractionProbe(axe=axe, max_clicks=60, max_depth=max_depth).run(
            page, baseline=baseline
        )
    ).findings

    # A set: one field can fail several rules (label *and* target-size), and
    # what is being measured is which levels were reached, not how many
    # violations each level happened to contain.
    reached = sorted(
        {
            int(m.group(1))
            for r in revealed
            if (m := re.match(r"#field-(\d)$", r.violation.target_selector))
        }
    )
    assert reached == list(range(1, max_depth + 1)), (
        f"max_depth={max_depth} should reach levels 1..{max_depth}, reached {reached}"
    )


async def test_concurrent_pages_each_get_their_own_state_count(browser, axe) -> None:  # type: ignore[no-untyped-def]
    """One probe serves every worker, so its result must not be shared state.

    The count was kept on the probe and read after the call. The probe is
    built once per crawl and used by two workers concurrently, so one page's
    pass reset the field before another read it: a scan whose log showed
    2,637 state-changing clicks recorded 2,585. A returned value cannot be
    raced, and this fails if the count ever moves back onto the instance.
    """
    probe = InteractionProbe(axe=axe, max_clicks=40)

    async def _scan(name: str):  # type: ignore[no-untyped-def]
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        try:
            await page.goto(_file_url(name))
            baseline = await axe.run(page, "AA")
            return await probe.run(page, baseline=baseline)
        finally:
            await context.close()

    # The same probe instance, two pages in flight at once.
    stress, hidden = await asyncio.gather(_scan("stress.html"), _scan("hidden_state.html"))

    assert stress.states > 0, "the busier fixture reached no states"
    assert hidden.states > 0, "the simpler fixture reached no states"
    # Each result describes its own page: a shared field would have made one
    # of these carry the other's total, or zero.
    assert stress.states != hidden.states or len(stress.findings) != len(hidden.findings)
    assert len(stress.findings) == len({f.violation.target_hash for f in stress.findings})


class _NoopAxe:
    async def run(self, *_args):  # type: ignore[no-untyped-def]
        return []


async def test_distinct_equal_named_controls_and_fixed_controls_are_clicked(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("""
        <main id="cards"></main><aside style="position:fixed;right:0;top:0">
        <button id="fixed" onclick="window.clicked.push('fixed')">Open help</button></aside>
        <label><input type="checkbox" onclick="window.clicked.push('checkbox')">Show details</label>
        <a href="#" role="button"
          onclick="event.preventDefault();window.clicked.push('anchor')">Expand</a>
        <script>
          window.clicked = [];
          for (let i=0; i<8; i++) {
            const button = document.createElement('button');
            button.className = 'card'; button.textContent = 'Details';
            button.onclick = () => window.clicked.push(i);
            document.getElementById('cards').append(button);
          }
        </script>
    """)
    await InteractionProbe(axe=_NoopAxe(), settle_ms=0).run(page)  # type: ignore[arg-type]
    clicked = await page.evaluate("window.clicked")
    assert clicked == [*range(8), "fixed", "checkbox", "anchor"]


async def test_nested_siblings_survive_escape_handling(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("""
        <button id="menu" onclick="panel.hidden=false">Menu</button>
        <div id="panel" hidden>
          <button id="first"
          onclick="window.clicked.push('first');this.dataset.used='1'">First</button>
          <button id="second"
          onclick="window.clicked.push('second');this.dataset.used='1'">Second</button>
        </div>
        <script>
          window.clicked=[];
          document.addEventListener('keydown', e => {if (e.key==='Escape') panel.hidden=true});
        </script>
    """)
    await InteractionProbe(axe=_NoopAxe(), settle_ms=0).run(page)  # type: ignore[arg-type]
    assert await page.evaluate("window.clicked") == ["first", "second"]


async def test_disabled_and_unsafe_actions_are_not_clicked(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("""
        <script>window.clicked=[]</script>
        <button onclick="window.clicked.push('subscription')">Subscribe now</button>
        <span id="pay-label">Make payment</span>
        <button aria-labelledby="pay-label"
          onclick="window.clicked.push('payment')">Continue</button>
        <button onclick="window.clicked.push('save')">Save changes</button>
        <button onclick="window.clicked.push('send')">Send invitation</button>
        <button disabled onclick="window.clicked.push('disabled')">More</button>
        <button aria-disabled="true" onclick="window.clicked.push('aria-disabled')">More</button>
        <form onsubmit="window.clicked.push('form');return false">
          <button>Continue</button><input type="submit" value="Continue">
        </form>
        <button
          onclick="if(confirm('Proceed?'))window.clicked.push('confirmed')">Show preview</button>
        <button onclick="window.clicked.push('safe')">Open details</button>
    """)
    await InteractionProbe(axe=_NoopAxe(), settle_ms=0).run(page)  # type: ignore[arg-type]
    assert await page.evaluate("window.clicked") == ["safe"]


async def test_network_writes_and_popups_are_blocked_without_affecting_other_tabs(browser) -> None:  # type: ignore[no-untyped-def]
    context = await browser.new_context(service_workers="block")
    requests: list[tuple[str, str]] = []
    html = """
        <button id="preview"
          onclick="fetch('/api/update', {method:'POST'}).catch(()=>{})">Preview</button>
        <button id="reset" onclick="fetch('/api/delete?id=1').catch(()=>{})">More details</button>
        <button id="popup" onclick="window.open('/payment')">View account</button>
        <button id="external"
          onclick="fetch('https://elsewhere.test/read').catch(()=>{})">Open resource</button>
        <button id="nav" onclick="location.href='/results'">Results</button>
        <button id="read"
          onclick="fetch('/api/content').then(()=>this.dataset.loaded='1')">Help</button>
    """

    async def fixture(route):  # type: ignore[no-untyped-def]
        requests.append((route.request.method, route.request.url))
        await route.fulfill(status=200, content_type="text/html", body=html)

    await context.route("**/*", fixture)
    page = await context.new_page()
    other = await context.new_page()
    try:
        await page.goto("https://fixture.test/")
        await other.goto("https://fixture.test/other")
        requests.clear()
        probe = InteractionProbe(axe=_NoopAxe(), settle_ms=10)  # type: ignore[arg-type]
        task = asyncio.create_task(probe.run(page))
        await asyncio.sleep(0.1)
        await other.evaluate("fetch('/unrelated', {method:'POST'})")
        result = await task
        assert ("POST", "https://fixture.test/unrelated") in requests
        assert ("GET", "https://fixture.test/api/content") in requests
        assert all(
            "/api/update" not in url
            and "/api/delete" not in url
            and "/payment" not in url
            and "/results" not in url
            and "elsewhere.test" not in url
            for _, url in requests
        )
        assert "https://fixture.test/results" in result.urls
        assert not any("/payment" in url for url in result.urls)
        # The temporary guard must not leak into later page work.
        await page.evaluate("fetch('/after', {method:'POST'})")
        assert ("POST", "https://fixture.test/after") in requests
    finally:
        await context.close()


async def test_time_budget_retains_earlier_evidence_and_removes_guard(page) -> None:  # type: ignore[no-untyped-def]
    async def fixture(route):  # type: ignore[no-untyped-def]
        await route.fulfill(status=200, content_type="text/html", body="<main>Fixture</main>")

    await page.context.route("**/*", fixture)
    await page.goto("https://fixture.test/")
    await page.set_content("<button onclick=\"this.textContent='Opened'\">Open</button>")

    class SlowAxe:
        async def run(self, *_args):  # type: ignore[no-untyped-def]
            await asyncio.sleep(10)
            return []

    result = await InteractionProbe(axe=SlowAxe(), timeout_s=0.3, settle_ms=0).run(page)  # type: ignore[arg-type]
    assert result.states == 1
    assert result.evaluated
    assert await page.evaluate("fetch('/after', {method:'POST'}).then(r => r.status)") == 200


async def test_focusable_categories_reopen_after_every_selection(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Missing ARIA roles must not prevent auditing a real custom menu."""
    await page.goto(_file_url("focusable_categories.html"))
    baseline = await axe.run(page, "AA")
    result = await InteractionProbe(axe=axe, settle_ms=10).run(page, baseline=baseline)
    assert await page.evaluate("window.selected") == [
        "My Favorites",
        "LSA-TS",
        "User Access",
        "History",
    ]
    assert await page.evaluate("window.openings") == 4
    assert await page.evaluate("window.focusTargetClicks") == 0
    assert {
        item.violation.target_selector
        for item in result.findings
        if item.violation.rule_id == "label"
    } == {"#category-0", "#category-1", "#category-2", "#category-3"}


async def test_reopening_categories_consumes_the_click_budget(page) -> None:  # type: ignore[no-untyped-def]
    await page.goto(_file_url("focusable_categories.html"))
    await InteractionProbe(axe=_NoopAxe(), max_clicks=4, settle_ms=10).run(page)  # type: ignore[arg-type]
    assert await page.evaluate("window.selected") == ["My Favorites", "LSA-TS"]
    assert await page.evaluate("window.openings") == 2


async def test_reopens_the_full_path_when_a_nested_menu_closes_all_ancestors(page) -> None:  # type: ignore[no-untyped-def]
    await page.set_content("""
        <button id="root">Categories</button>
        <main id="content"></main>
        <script>
          window.selected=[]; window.rootOpenings=0; window.subOpenings=0;
          root.onclick = () => {
            window.rootOpenings++;
            const parent=document.createElement('div');
            parent.id='parent-'+window.rootOpenings;
            const opener=document.createElement('button');
            opener.textContent='Departments';
            opener.onclick=() => {
              window.subOpenings++;
              const sub=document.createElement('div');
              sub.id='sub-'+window.subOpenings;
              ['First', 'Second'].forEach(name => {
                const item=document.createElement('button'); item.textContent=name;
                item.onclick=() => {
                  window.selected.push(name); content.textContent=name;
                  sub.remove(); parent.remove();
                };
                sub.append(item);
              });
              document.body.append(sub);
            };
            parent.append(opener); document.body.append(parent);
          };
        </script>
    """)
    await InteractionProbe(axe=_NoopAxe(), settle_ms=10).run(page)  # type: ignore[arg-type]
    assert await page.evaluate("window.selected") == ["First", "Second"]
    assert await page.evaluate("[window.rootOpenings, window.subOpenings]") == [2, 2]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_coverage_counts_operated_controls_and_names_the_bound(page, axe) -> None:  # type: ignore[no-untyped-def]
    """A capped sweep must report what it left alone, not just what it did.

    ``hidden_state.html`` holds ten same-shaped calendar buttons plus a
    blocked "Sign out". With the repeat cap at three, most of those controls
    are discovered and never operated — which is exactly the case a coverage
    number must not round up to "checked".
    """
    await page.goto(_file_url("hidden_state.html"))
    baseline = await axe.run(page, "AA")

    result = await InteractionProbe(axe=axe, max_repeated=3).run(page, baseline=baseline)

    assert result.evaluated
    assert result.controls_operated < result.controls_discovered
    assert result.controls_operated <= result.clicks_succeeded <= result.clicks_attempted
    assert result.blocked_controls >= 1
    assert "repeated_controls" in result.limits


@pytest.mark.integration
@pytest.mark.asyncio
async def test_controls_revealed_by_a_click_are_counted_as_discovered(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Depth-limited exploration still records the controls it uncovered."""
    await page.goto(_file_url("nested_depth.html"))
    baseline = await axe.run(page, "AA")

    shallow = await InteractionProbe(axe=axe, max_depth=1).run(page, baseline=baseline)
    await page.reload()
    deep = await InteractionProbe(axe=axe, max_depth=4).run(page, baseline=baseline)

    # The depth-1 sweep opens the first level and sees what it exposed
    # without being allowed to press it, so discovery exceeds clicks and the
    # bound that stopped it is named.
    assert shallow.controls_discovered > shallow.controls_operated
    assert "depth" in shallow.limits
    assert deep.controls_operated > shallow.controls_operated


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_dialog_is_closed_before_the_next_control_is_used(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Escape-closable and button-closable dialogs must both be cleared.

    The fixture's veil covers the page whenever a dialog is up, so the plain
    control at the end can only be clicked if both dialogs were actually
    dismissed first. Its counter is the assertion.
    """
    await page.goto(_file_url("modal_dismissal.html"))
    baseline = await axe.run(page, "AA")

    # Without the undismissable one in play, the sweep must run to the end.
    await page.evaluate("() => document.getElementById('stuck').remove()")
    result = await InteractionProbe(axe=axe).run(page, baseline=baseline)

    assert result.dialogs_opened == 2, "both dialogs should have been opened"
    assert result.dialogs_stuck == 0
    assert "dialog_not_dismissed" not in result.limits
    clicks = await page.evaluate("() => document.getElementById('after-count').textContent")
    assert int(clicks) == 1, (
        "the control after the dialogs was never reached: a dialog was left open"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_dialog_that_will_not_close_stops_the_page_and_is_reported(page, axe) -> None:  # type: ignore[no-untyped-def]
    """The stuck dialog must end the sweep rather than click through an overlay.

    Its only exit is labelled "Delete everything", so the probe has no safe
    way out and must say so instead of pressing it.
    """
    await page.goto(_file_url("modal_dismissal.html"))
    baseline = await axe.run(page, "AA")
    # Put the undismussable dialog first so there is still page left to lose.
    await page.evaluate(
        "() => { const s = document.getElementById('stuck');"
        " s.parentElement.insertBefore(s, document.getElementById('escapable')); }"
    )

    result = await InteractionProbe(axe=axe).run(page, baseline=baseline)

    assert result.dialogs_stuck == 1
    assert "dialog_not_dismissed" in result.limits
    assert "did not close" in result.detail
    assert "Open undismissable dialog" in result.detail
    # The destructive control inside it was never used to tidy up.
    assert await page.evaluate("() => document.getElementById('m-stuck').hasAttribute('data-open')")
    # And the sweep stopped instead of clicking the overlay.
    clicks = await page.evaluate("() => document.getElementById('after-count').textContent")
    assert int(clicks) == 0, "clicking continued past an open modal"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_controls_inside_a_dialog_are_still_explored_before_it_closes(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Closing the dialog must not cost the coverage inside it.

    Each dialog holds an unlabelled input, which axe only sees while the
    dialog is open.
    """
    await page.goto(_file_url("modal_dismissal.html"))
    baseline = await axe.run(page, "AA")

    result = await InteractionProbe(axe=axe).run(page, baseline=baseline)

    revealed = {finding.violation.rule_id for finding in result.findings}
    assert "label" in revealed, "the dialog's unlabelled input was never scanned"
    assert result.states >= 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_dialog_ignoring_escape_is_closed_by_its_own_close_control(page, axe) -> None:  # type: ignore[no-untyped-def]
    """Escape is not the only exit, so a dialog that ignores it still closes.

    ``max_depth=1`` stops the nested sweep from entering the dialog, so the
    dialog's own Close button cannot be pressed as ordinary exploration.
    Anything that closes it here is the dismissal path.
    """
    await page.goto(_file_url("modal_dismissal.html"))
    baseline = await axe.run(page, "AA")
    await page.evaluate(
        "() => { for (const id of ['escapable', 'stuck']) document.getElementById(id).remove(); }"
    )

    result = await InteractionProbe(axe=axe, max_depth=1).run(page, baseline=baseline)

    assert result.dialogs_opened == 1
    assert result.dialogs_stuck == 0
    assert not await page.evaluate(
        "() => document.getElementById('m-button').hasAttribute('data-open')"
    )
    clicks = await page.evaluate("() => document.getElementById('after-count').textContent")
    assert int(clicks) == 1, "the control after the dialog was never reached"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_non_modal_dialog_never_stops_the_page(page, axe) -> None:  # type: ignore[no-untyped-def]
    """role="dialog" alone is not modal, and must not cost the rest of the page.

    Regression: treating every visible dialog as blocking halted a sweep on
    an ordinary inline panel that covered nothing, losing every control after
    it. Only aria-modal and a native showModal() dialog block.
    """
    await page.goto(_file_url("modal_dismissal.html"))
    baseline = await axe.run(page, "AA")
    await page.evaluate(
        "() => { for (const id of ['escapable', 'button-only', 'stuck'])"
        " document.getElementById(id).remove(); }"
    )

    result = await InteractionProbe(axe=axe).run(page, baseline=baseline)

    assert result.dialogs_opened == 0, "a non-modal dialog was treated as blocking"
    assert result.dialogs_stuck == 0
    assert "dialog_not_dismissed" not in result.limits
    # It stayed open, and the sweep carried on regardless.
    assert await page.evaluate("() => document.getElementById('m-plain').hasAttribute('data-open')")
    clicks = await page.evaluate("() => document.getElementById('after-count').textContent")
    assert int(clicks) == 1
