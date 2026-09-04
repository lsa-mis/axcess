"""Pure-logic tests for the interaction probe — no browser required."""

from __future__ import annotations

import inspect

from audit.analyzer.axe import AxeViolation
from audit.analyzer.interaction import InteractionProbe, RevealedViolation
from audit.analyzer.interaction.probe import _signature


def _violation(rule_id: str = "label", selector: str = "input#x") -> AxeViolation:
    return AxeViolation(
        rule_id=rule_id,
        impact="serious",
        help="Form elements must have labels",
        help_url="https://example.test/label",
        wcag_sc="4.1.2",
        wcag_scs="4.1.2",
        wcag_level="A",
        target_selector=selector,
        failure_summary="no label",
        html_snippet="<input id=x>",
    )


def test_signature_collapses_digits_so_one_calendar_is_one_shape() -> None:
    assert _signature("button#day-1") == _signature("button#day-365")
    # Different shapes must stay distinct, or the cap would suppress
    # unrelated controls after three clicks.
    assert _signature("button#day-1") != _signature("button#month-1")


def test_signature_is_case_insensitive() -> None:
    assert _signature("BUTTON#Day-1") == _signature("button#day-1")


def test_blocked_labels_match_as_substrings_case_insensitively() -> None:
    probe = InteractionProbe(axe=None)  # type: ignore[arg-type]
    assert probe._is_blocked("Sign out of all devices")
    assert probe._is_blocked("DELETE THIS ROW")
    assert probe._is_blocked("Remove attachment")
    assert not probe._is_blocked("Add another guest")
    assert not probe._is_blocked("Show more results")


def test_global_controls_are_keyed_without_the_page_url() -> None:
    """A nav button is operated once per crawl, not once per page."""
    probe = InteractionProbe(axe=None)  # type: ignore[arg-type]
    control = {"tag": "button", "label": "Menu", "isGlobal": True, "selector": "button.nav"}
    key_a = probe._interaction_key(control, "https://example.test/a")
    key_b = probe._interaction_key(control, "https://example.test/b")
    assert key_a == key_b


def test_page_local_controls_are_keyed_per_page() -> None:
    probe = InteractionProbe(axe=None)  # type: ignore[arg-type]
    control = {"tag": "button", "label": "Expand", "isGlobal": False, "selector": "button.x"}
    key_a = probe._interaction_key(control, "https://example.test/a")
    key_b = probe._interaction_key(control, "https://example.test/b")
    assert key_a != key_b


def test_revealed_violation_delegates_the_screenshot_keys() -> None:
    """The screenshot pass treats every finding type identically, so a
    RevealedViolation must expose the same two attributes as the rest."""
    v = _violation()
    revealed = RevealedViolation(violation=v, revealed_by="Add another guest")
    assert revealed.target_hash == v.target_hash
    assert revealed.target_selector == v.target_selector


def test_revealed_by_is_not_part_of_the_dedupe_key() -> None:
    """Two controls revealing the same defective markup are one defect."""
    v = _violation()
    a = RevealedViolation(violation=v, revealed_by="Open menu")
    b = RevealedViolation(violation=v, revealed_by="Open dialog")
    assert a.target_hash == b.target_hash


def test_key_cannot_depend_on_recursion_depth() -> None:
    """A control is the same control however deep the sweep that found it.

    Depth used to be part of this key, and because the claim was also
    recorded after the recursive call rather than before it, one control got
    operated once per level. Asserting on the signature keeps depth out of
    the identity structurally, rather than trusting a caller to stop passing
    it.
    """
    params = list(inspect.signature(InteractionProbe._interaction_key).parameters)
    assert params == ["self", "control", "pinned"]


def test_equal_names_at_different_dom_locations_are_distinct() -> None:
    probe = InteractionProbe(axe=None)  # type: ignore[arg-type]
    first = {"tag": "button", "label": "Details", "isGlobal": False, "selector": "#first"}
    second = {**first, "selector": "#second"}
    assert probe._interaction_key(first, "https://example.test/") != probe._interaction_key(
        second, "https://example.test/"
    )


def test_sensitive_actions_are_blocked() -> None:
    probe = InteractionProbe(axe=None)  # type: ignore[arg-type]
    for label in (
        "Subscribe now",
        "PAYMENT",
        "save_changes",
        "Send invitation",
        "Upload file",
        "Confirm transfer",
        "Start trial",
        "Grant access",
    ):
        assert probe._is_blocked(label), label


def test_discovered_urls_exclude_sensitive_actions_and_nonweb_schemes() -> None:
    from audit.analyzer.interaction import DEFAULT_BLOCKED_LABELS
    from audit.analyzer.interaction.safety import safe_url

    for url in (
        "https://example.test/%64elete",
        "https://example.test/action?do=payment",
        "https://user:password@example.test/",
        "javascript:alert(1)",
        "mailto:someone@example.test",
        "https://example.test/sign-out",
    ):
        assert not safe_url(url, DEFAULT_BLOCKED_LABELS), url
    assert safe_url("https://example.test/results?q=trees", DEFAULT_BLOCKED_LABELS)


async def test_unguarded_service_worker_context_is_not_reported_as_checked() -> None:
    from types import SimpleNamespace

    page = SimpleNamespace(
        url="https://example.test/", context=SimpleNamespace(service_workers=[object()])
    )
    result = await InteractionProbe(axe=None).run(page)  # type: ignore[arg-type]
    assert not result.evaluated
    assert result.states == 0
    assert result.findings == ()
