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
        # Through a shadow root or a frame: not a plain path the page can resolve.
        ('{"type":"element","path":"/html[1]/body[1]/x-app[1]/#shadow-root/button[1]"}', None),
        ('{"type":"element","path":"/html[1]/body[1]\\"]|//*["}', None),
        ("Alfa target unavailable; see the stored evidence.", None),
    ],
)
def test_alfa_xpath_reads_only_a_plain_element_path(target_hint: str, expected: str | None) -> None:
    assert alfa_xpath(target_hint) == expected
