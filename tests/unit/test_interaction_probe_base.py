"""Pure-logic tests for the interaction probe — no browser required."""

from __future__ import annotations

import inspect

from audit.analyzer.axe import AxeViolation
from audit.analyzer.interaction import (
    InteractionProbe,
    InteractionResult,
    RevealedViolation,
)
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


def test_state_key_is_optional_for_producers_that_capture_nothing() -> None:
    """``search.py`` builds these positionally with two arguments.

    ``state_key`` identifies a captured DOM state, and the configured-search
    pass captures none, so it must stay defaulted rather than becoming a
    required third positional.
    """
    revealed = RevealedViolation(_violation(), "Configured search")
    assert revealed.state_key == ""


def test_captures_are_a_subset_of_the_states_counter() -> None:
    """``states`` counts every DOM-changing click; ``captures`` only the ones
    that held a new defect. Conflating them would overstate either coverage or
    storage, so the default result keeps both at zero."""
    result = InteractionResult()
    assert result.states == 0
    assert result.captures == ()


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


def test_every_probe_is_built_with_an_explicit_capture_decision() -> None:
    """Storing revealed-state markup must never be decided by the default.

    The probe is constructed in more than one place, and the authenticated
    scan builds its own rather than going through the orchestrator. When the
    storage opt-out was first wired it reached only the orchestrator's, so a
    login scan that had declined to store rendered pages still captured the
    states behind its controls -- post-authentication documents, from the one
    kind of scan where that matters most.

    Defaults cannot enforce that, because the default has to stay ``True`` for
    an ordinary scan. Naming the argument at every call site can, and this is
    the check that says so.
    """
    import ast
    from pathlib import Path

    source_root = Path(__file__).resolve().parents[2] / "src"
    missing: list[str] = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "InteractionProbe":
                continue
            if not any(kw.arg == "capture_states" for kw in node.keywords):
                missing.append(f"{path.relative_to(source_root)}:{node.lineno}")

    assert not missing, (
        "InteractionProbe built without an explicit capture_states decision at: "
        + ", ".join(missing)
    )
