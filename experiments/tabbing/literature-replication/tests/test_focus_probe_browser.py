"""Behavioural tests for the focus probe, executed in the installed browser.

`tests/test_focus_probe.py` asserts on the *source text* of `FOCUS_PROBE_JS`.
Those assertions passed while the probe collapsed every direct child of a shadow
root onto one identity (gate-2 finding R4), and would pass again after the same
regression. A test that cannot fail when the behaviour is wrong is not evidence.

Everything here runs the real probe against a real DOM in Chromium and fails
when two distinct elements receive one identity, or when an unsupported scope
returns a colliding value instead of an explicit exclusion marker.
"""

from __future__ import annotations

import pytest

from tools import replay

playwright_sync = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    with playwright_sync.sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def probe(page) -> str:
    return page.evaluate(replay.FOCUS_PROBE_JS)


def identity_of(page, focus_js: str) -> str:
    """Focus the element selected by `focus_js`, then ask the probe who it is."""
    page.evaluate(f"() => {{ ({focus_js}).focus(); }}")
    return probe(page)


SIBLINGS_IN_ONE_SHADOW_ROOT = """
<div id="host"></div>
<script>
  const r = document.getElementById('host').attachShadow({mode: 'open'});
  r.innerHTML = '<button id="a">A</button><button id="b">B</button>';
</script>
"""


def test_two_buttons_in_one_shadow_root_get_two_identities(page):
    page.set_content(SIBLINGS_IN_ONE_SHADOW_ROOT)
    root = "document.getElementById('host').shadowRoot"
    first = identity_of(page, f"{root}.querySelector('#a')")
    second = identity_of(page, f"{root}.querySelector('#b')")
    assert first != second, f"identity collapsed: both siblings reported {first!r}"


NESTED_SHADOW_ROOTS = """
<div id="host"></div>
<script>
  const outer = document.getElementById('host').attachShadow({mode: 'open'});
  outer.innerHTML = '<x-one></x-one><x-two></x-two>';
  for (const name of ['x-one', 'x-two']) {
    const inner = outer.querySelector(name).attachShadow({mode: 'open'});
    inner.innerHTML = '<button>deep</button>';
  }
</script>
"""


def test_buttons_in_two_inner_shadow_roots_get_two_identities(page):
    """The hosts are siblings in one outer root, so the collapse recurses."""
    page.set_content(NESTED_SHADOW_ROOTS)
    outer = "document.getElementById('host').shadowRoot"
    first = identity_of(page, f"{outer}.querySelector('x-one').shadowRoot.querySelector('button')")
    second = identity_of(page, f"{outer}.querySelector('x-two').shadowRoot.querySelector('button')")
    assert first != second, f"identity collapsed: both deep buttons reported {first!r}"


def serve(page, pages: dict[str, str]) -> None:
    """Fulfil the given URLs from memory. Anything else is denied.

    Routing is what lets a test hold two real origins without a network.
    """
    def handler(route):
        body = pages.get(route.request.url)
        if body is None:
            route.abort()
        else:
            route.fulfill(status=200, content_type="text/html", body=body)

    page.context.route("**/*", handler)


INNER = "<button id='a'>A</button><button id='b'>B</button>"


def framed(src: str) -> dict[str, str]:
    return {
        "http://a.test/": f"<p>outer</p><iframe id='f' src='{src}'></iframe>",
        src: INNER,
    }


def test_two_buttons_in_a_same_origin_frame_get_two_identities(page):
    serve(page, framed("http://a.test/inner"))
    page.goto("http://a.test/")
    inner = page.frame(url="http://a.test/inner")
    ids = []
    for sel in ("#a", "#b"):
        inner.evaluate(f"() => document.querySelector('{sel}').focus()")
        ids.append(probe(page))
    assert ids[0] != ids[1], f"identity collapsed: both frame buttons reported {ids[0]!r}"


def test_a_cross_origin_frame_is_marked_unsupported_not_silently_collapsed(page):
    """A scope the probe cannot enter must announce itself.

    Two stops inside an unreadable frame do share one string -- that is
    unavoidable from this context -- but the string says so, so a trail can
    exclude it instead of counting it as an ordinary focus stop.
    """
    serve(page, framed("http://b.test/inner"))
    page.goto("http://a.test/")
    inner = page.frame(url="http://b.test/inner")
    ids = []
    for sel in ("#a", "#b"):
        inner.evaluate(f"() => document.querySelector('{sel}').focus()")
        ids.append(probe(page))
    # The constant is what the adjudicator screens trails for; if the probe and
    # `replay.OPAQUE_SCOPE` ever drift apart, that screen stops working.
    assert all(replay.OPAQUE_SCOPE in i for i in ids), ids
    assert all(i != "1:body/1:iframe" for i in ids), ids


def test_tagging_does_not_change_identities_in_shadow_or_frame_scopes(page):
    """Perturbation control: the census attribute must be invisible to identity.

    This is the G1c assumption, exercised on the two scopes R4 was about. The
    census-applied assertion keeps the control from passing vacuously.
    """
    serve(page, {
        "http://a.test/": (
            "<div id='host'></div><iframe id='f' src='http://a.test/inner'></iframe>"
            "<script>const r = document.getElementById('host')"
            ".attachShadow({mode:'open'});"
            "r.innerHTML = \"<button id='a'>A</button><button id='b'>B</button>\";"
            "</script>"
        ),
        "http://a.test/inner": INNER,
    })
    page.goto("http://a.test/")
    inner = page.frame(url="http://a.test/inner")
    root = "document.getElementById('host').shadowRoot"

    def trail():
        seen = []
        for sel in ("#a", "#b"):
            page.evaluate(f"() => {root}.querySelector('{sel}').focus()")
            seen.append(probe(page))
            inner.evaluate(f"() => document.querySelector('{sel}').focus()")
            seen.append(probe(page))
        return seen

    before = trail()
    tagged = page.evaluate(replay.NEUTRAL_CENSUS_JS, replay.CENSUS_ATTR)
    assert tagged > 0, "census applied no attributes; the control would be vacuous"
    assert before == trail()
    assert len(set(before)) == 4, f"identities collapsed before tagging: {before}"
