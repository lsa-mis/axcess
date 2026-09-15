"""Seeded-defect tests for the G1c validity gate.

The adjudicator's job is to refuse to draw a conclusion from a run that is not
interpretable. Asserting that it reports the right verdict on the *real* data
proves little: the real data is valid, so a gate that always said "valid" would
pass. These tests mutate the recorded runs with defects whose correct verdict is
known in advance, which is the only way to show the gate can actually fire.

This is the answer-key form of verification. It exists because the previous
round of focus-probe tests asserted on the source text of a script and passed
while the defect they were meant to catch was present.

No browser, no network: pure adjudication over mutated records.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tools.adjudicate_g1c import adjudicate

DERIVED = pathlib.Path(__file__).resolve().parent.parent / "derived" / "feasibility.json"


@pytest.fixture(scope="module")
def real_rows() -> list[dict]:
    return json.loads(DERIVED.read_text())


def _find(rows: list[dict], subject: str, tagged: bool, repeat: int) -> dict:
    for r in rows:
        if (r["subject"], r["tagged"], r["repeat"]) == (subject, tagged, repeat):
            return r
    raise LookupError((subject, tagged, repeat))


def _headline(rows: list[dict]) -> str:
    """The verdict class, without the explanatory tail."""
    return adjudicate(rows).verdict.split("--")[0].strip()


# --------------------------------------------------------------------------
# Control: the gate must not fire on the data it was built against.
# --------------------------------------------------------------------------


def test_unmutated_run_is_adjudicated_and_h0_survives(real_rows):
    """Without this, a gate that voided everything would pass every other test."""
    assert _headline(real_rows) == "H0 NOT FALSIFIED"


# --------------------------------------------------------------------------
# Registered voiding conditions (PREREGISTRATION-G1c.md)
# --------------------------------------------------------------------------


def test_p1_failure_voids_rather_than_reporting_h0(real_rows):
    """Repeats that disagree make the comparison uninterpretable, not falsified.

    This is the defect Codex found: the earlier adjudicator printed H0 survival
    even when reproducibility failed.
    """
    rows = copy.deepcopy(real_rows)
    _find(rows, "craigslist", False, 1)["focus_trail"][0] = "MUTATED"
    assert _headline(rows) == "VOID"


def test_p3_failure_voids_the_run(real_rows):
    """A probe returning a constant would make H0 pass trivially."""
    rows = copy.deepcopy(real_rows)
    for record in rows:
        record["focus_trail"] = ["SAME"] * len(record["focus_trail"])
    assert _headline(rows) == "VOID"


# --------------------------------------------------------------------------
# The gate must still be able to falsify. A gate that only voids is useless.
# --------------------------------------------------------------------------


def test_diverging_arms_falsify_h0_and_are_not_voided(real_rows):
    rows = copy.deepcopy(real_rows)
    for repeat in (0, 1):
        _find(rows, "craigslist", True, repeat)["focus_trail"][3] = "DIVERGED"
    assert _headline(rows) == "H0 FALSIFIED"


# --------------------------------------------------------------------------
# Matrix integrity: the pre-registration fixes the runs in advance.
# --------------------------------------------------------------------------


def test_missing_cell_voids(real_rows):
    rows = copy.deepcopy(real_rows)
    rows.remove(_find(rows, "coronavirus", True, 1))
    assert _headline(rows) == "VOID"


def test_duplicate_record_voids(real_rows):
    """The earlier adjudicator silently overwrote duplicates."""
    rows = copy.deepcopy(real_rows)
    rows.append(copy.deepcopy(_find(rows, "citiprogram", False, 0)))
    assert _headline(rows) == "VOID"


def test_short_trail_voids(real_rows):
    rows = copy.deepcopy(real_rows)
    record = _find(rows, "citiprogram", True, 0)
    record["focus_trail"] = record["focus_trail"][:9]
    assert _headline(rows) == "VOID"


def test_failed_run_is_not_adjudicated_as_evidence(real_rows):
    rows = copy.deepcopy(real_rows)
    _find(rows, "coronavirus", False, 0)["ok"] = False
    assert _headline(rows) == "VOID"
