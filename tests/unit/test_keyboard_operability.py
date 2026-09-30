"""Pure parts of the SC 2.1.1 mouse-only control probe (no browser)."""

from __future__ import annotations

from audit.analyzer.keyboard.base import RULE_NO_KEY_HANDLER, RULE_UNREACHABLE
from audit.analyzer.keyboard.operability import (
    KeyboardOperabilityProbe,
    OperabilityLead,
    OperabilityResult,
    _describe,
    _origin,
    _similar,
)


def _lead(**overrides: object) -> OperabilityLead:
    base: dict[str, object] = {
        "kind": "unreachable",
        "selector": "div#fake",
        "html": "<div id='fake'>Open grades</div>",
        "name": "open grades",
        "signals": ("mouse listener",),
        "strength": 3,
        "testable": True,
    }
    return OperabilityLead(**{**base, **overrides})  # type: ignore[arg-type]


def test_a_static_lead_is_an_sc_2_1_1_row_that_says_it_was_not_operated() -> None:
    finding = KeyboardOperabilityProbe()._finding(_lead())
    row = finding.to_repo_kwargs()
    assert row["rule_id"] == RULE_UNREACHABLE
    assert (row["wcag_sc"], row["wcag_level"], row["pipeline"]) == ("2.1.1", "A", "keyboard")
    assert "Static evidence only" in row["failure_summary"]
    assert row["help_url"].endswith("/keyboard.html")


def test_a_confirmed_lead_leads_with_its_measurement() -> None:
    lead = _lead(kind="no_key_handler", verdict="confirmed", evidence="Measured: it did X.")
    finding = KeyboardOperabilityProbe()._finding(lead)
    assert finding.rule_id == RULE_NO_KEY_HANDLER
    assert finding.failure_summary.startswith("Measured: it did X.")
    assert "Static evidence only" not in finding.failure_summary


def test_dismissed_leads_are_not_reported() -> None:
    result = OperabilityResult(leads=[_lead(), _lead(selector="b", verdict="dismissed")])
    assert [lead.selector for lead in result.reported()] == ["div#fake"]


def test_the_destructive_word_list_is_the_interaction_probes() -> None:
    probe = KeyboardOperabilityProbe()
    assert probe._is_blocked("Delete account")
    assert probe._is_blocked("sign-out")
    assert not probe._is_blocked("Open grades")


def test_effects_are_the_same_when_most_changed_items_agree() -> None:
    click = ["+e:/1DIV", "+t:/1DIV/0:5", "-e:/2P"]
    assert _similar(click, ["+e:/1DIV", "+t:/1DIV/0:5"])
    assert not _similar(click, ["+e:/9UL"])
    assert _similar([], [])


def test_an_effect_is_described_in_words() -> None:
    assert _describe(["+e:/1DIV", "+e:/2DIV"], 0) == "showed 2 elements"
    assert _describe(["-e:/1DIV"], 1) == (
        "hid 1 element and sent a request, opened a dialog or window, or started navigation"
    )
    assert _describe(["+v:0:12:1"], 0) == "changed text or state on the page"


def test_origin_is_scheme_and_host() -> None:
    assert _origin("https://Example.test:8443/a?b") == "https://example.test:8443"
    assert _origin("about:blank") == ""


def test_delegation_selectors_are_read_from_a_handlers_source() -> None:
    from audit.analyzer.keyboard.operability import selectors_in_handler

    source = """function(e){var t=e.target.closest?e.target.closest('.row-action'):null;
      if(e.target.matches("[data-action]"))go();if(e.target.id==='by-id')open();
      if(t.classList.contains('card'))x();if($(e.target).is('.jq a'))y();
      if($(e.target).hasClass("menu-item"))z();if(e.target.hasAttribute('data-toggle'))w();}"""
    assert selectors_in_handler(source) == [
        ".row-action",
        "[data-action]",
        ".jq a",
        ".card",
        "[data-toggle]",
        "#by-id",
        ".menu-item",
    ]


def test_a_click_tracker_reading_an_attribute_is_not_delegation() -> None:
    from audit.analyzer.keyboard.operability import selectors_in_handler

    source = "function(e){track(e.target.getAttribute('data-automation-id'))}"
    assert selectors_in_handler(source) == []
