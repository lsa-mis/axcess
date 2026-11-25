"""Settling one page's Alfa checks: load baseline, revealed states, reasons."""

from __future__ import annotations

import asyncio

import pytest

from audit.analyzer.alfa import AlfaError, AlfaFinding, AlfaResult
from audit.analyzer.alfa_states import AlfaPageChecks, AlfaStateCheck, alfa_xpath, settle


def _finding(target: str, outcome: str = "failed") -> AlfaFinding:
    return AlfaFinding(
        rule_id="sia-r68",
        rule_uri="https://alfa.siteimprove.com/rules/sia-r68",
        outcome=outcome,  # type: ignore[arg-type]
        mode="automatic",
        wcag_sc="1.3.1",
        wcag_scs="1.3.1",
        wcag_level="A",
        help="help",
        failure_summary="summary",
        target_hint=target,
        evidence_json="{}",
        target_identity=target,
    )


def _result(*findings: AlfaFinding) -> AlfaResult:
    return AlfaResult(
        url="https://example.test/",
        status=200,
        findings=findings,
        failed_total=sum(1 for f in findings if f.outcome == "failed"),
        cant_tell_total=sum(1 for f in findings if f.outcome == "cant_tell"),
        truncated=False,
    )


def _done(value: AlfaResult | BaseException) -> asyncio.Task[AlfaResult]:
    async def run() -> AlfaResult:
        if isinstance(value, BaseException):
            raise value
        return value

    return asyncio.get_running_loop().create_task(run())


@pytest.mark.asyncio
async def test_a_state_adds_only_what_load_and_earlier_states_did_not_show() -> None:
    menu = _finding("/html/body/nav/ul")
    dialog = _finding("/html/body/div[2]", outcome="cant_tell")
    checks = AlfaPageChecks(load=_done(_result(_finding("/html/body/main"))))
    checks.states.append(AlfaStateCheck(_done(_result(_finding("/html/body/main"), menu)), "Menu"))
    checks.states.append(AlfaStateCheck(_done(_result(menu, dialog)), "Open dialog", "k2"))

    outcome = await settle(checks)

    assert [(r.finding.target_hint, r.revealed_by) for r in outcome.revealed] == [
        ("/html/body/nav/ul", "Menu"),
        ("/html/body/div[2]", "Open dialog"),
    ]
    assert outcome.revealed[1].state_key == "k2"
    assert outcome.states_checked == 2
    assert (outcome.revealed_failed, outcome.revealed_cant_tell) == (1, 1)


@pytest.mark.asyncio
async def test_a_failed_state_keeps_its_reason() -> None:
    checks = AlfaPageChecks(load=_done(_result()))
    checks.states.append(AlfaStateCheck(_done(AlfaError("Alfa took longer than 75 seconds")), "X"))
    checks.state_errors.append("The page is too large for Alfa")

    outcome = await settle(checks)

    assert outcome.states_checked == 0
    assert outcome.state_errors == (
        "The page is too large for Alfa",
        "Alfa took longer than 75 seconds",
    )


@pytest.mark.asyncio
async def test_without_a_load_result_states_are_not_reported_as_revealed() -> None:
    """Without the baseline, every occurrence would look revealed by a click."""
    checks = AlfaPageChecks(load=_done(AlfaError("snapshot failed")))
    checks.states.append(AlfaStateCheck(_done(_result(_finding("/html/body"))), "Menu"))

    outcome = await settle(checks)

    assert outcome.load is None
    assert outcome.load_error == "snapshot failed"
    assert outcome.revealed == ()
    assert len(outcome.state_errors) == 1


@pytest.mark.asyncio
async def test_an_unexpected_error_is_a_reason_not_a_clean_result() -> None:
    checks = AlfaPageChecks(load=_done(RuntimeError("boom")))

    outcome = await settle(checks)

    assert outcome.load is None
    assert outcome.load_error is not None
    assert "RuntimeError: boom" in outcome.load_error


@pytest.mark.parametrize(
    ("target_hint", "expected"),
    [
        (
            '{"type":"element","path":"/html[1]/body[1]/main[1]/button[2]"}',
            "/html[1]/body[1]/main[1]/button[2]",
        ),
        # A text target (sia-r69, contrast): the element holding the text.
        # Report 79's Qualtrics page, 2026-11-25.
        (
            '{"type":"text","path":"/html[1]/body[1]/div[1]/main[1]/p[3]/a[1]/text()[1]",'
            '"data":"4HELP@umich.edu"}',
            "/html[1]/body[1]/div[1]/main[1]/p[3]/a[1]",
        ),
        # Through a shadow root or a frame: not a plain path the page can resolve.
        ('{"type":"element","path":"/html[1]/body[1]/x-app[1]/#shadow-root/button[1]"}', None),
        ('{"type":"element","path":"/html[1]/body[1]\\"]|//*["}', None),
        ("Alfa target unavailable; see the stored evidence.", None),
    ],
)
def test_alfa_xpath_reads_only_a_plain_path_to_an_element(
    target_hint: str, expected: str | None
) -> None:
    assert alfa_xpath(target_hint) == expected


def test_a_saved_state_document_uses_its_saved_css_like_the_inspector() -> None:
    from audit.crawler.js_fetcher import _saved_state_document
    from audit.crawler.style_snapshot import CapturedSheet, StyleSnapshot

    html = (
        '<html><head><meta http-equiv="Content-Security-Policy" content="style-src \'self\'">'
        '<link rel="stylesheet" href="/site.css"><link rel="icon" href="/i.png">'
        "<style>p{color:blue}</style></head><body><p>x</p></body></html>"
    )
    styles = StyleSnapshot(
        sheets=(CapturedSheet(css="p{color:red}", media="", source_url=None),), complete=True
    )

    document = _saved_state_document(html, styles)

    assert "Content-Security-Policy" not in document
    assert "/site.css" not in document and "color:blue" not in document
    assert '<link rel="icon" href="/i.png">' in document
    assert document.index("p{color:red}") < document.index("</head>")
    # Without saved CSS the page's own stylesheets stay.
    assert "/site.css" in _saved_state_document(html, None)


def test_only_focus_visible_screenshots_from_a_scan_that_took_them_focused_say_so() -> None:
    from audit.analyzer.alfa_states import screenshot_focused

    focused_scan = {"alfa_focus_screenshots": True}
    assert screenshot_focused(focused_scan, "alfa", "sia-r65")
    assert not screenshot_focused(focused_scan, "alfa", "sia-r69")
    assert not screenshot_focused(focused_scan, "axe", "sia-r65")
    # A report made before 2026-11-25: its pictures were not focused.
    assert not screenshot_focused({}, "alfa", "sia-r65")
