"""Tests for the G1c adjudicator (gate-2 finding R3).

`PREREGISTRATION-G1c.md` fixes the matrix in advance -- three subjects, two
arms, two repeats, 15 `Tab` presses -- and says that if prediction 1 or 3 fails
the run is void and no conclusion about H0 may be drawn. The adjudicator printed
P1, P2 and P3 independently, so a void run could still print H0 survival, and it
indexed records into a dict that silently overwrote duplicates.

These tests build synthetic record sets and assert on the disposition, not on
what the script prints about a file that happens to be on disk.
"""

from __future__ import annotations

from tools import adjudicate_g1c as adj

SUBJECTS = ("citiprogram", "coronavirus", "craigslist")


def record(subject, tagged, repeat, trail=None):
    trail = trail if trail is not None else [f"{i}:a" for i in range(15)]
    return {
        "subject": subject,
        "tagged": tagged,
        "repeat": repeat,
        "ok": True,
        "focus_trail": list(trail),
    }


def registered_matrix(**overrides):
    rows = []
    for s in SUBJECTS:
        for tagged in (False, True):
            for repeat in (0, 1):
                rows.append(record(s, tagged, repeat))
    return rows


def test_a_duplicate_record_makes_the_run_invalid():
    """Two records for one cell were silently collapsed into whichever came last."""
    rows = registered_matrix()
    rows.append(record("craigslist", True, 1, trail=[f"{i}:b" for i in range(15)]))
    result = adj.adjudicate(rows)
    assert not result.valid
    assert any("duplicate" in p.lower() for p in result.problems), result.problems


def test_a_missing_cell_makes_the_run_invalid():
    rows = [r for r in registered_matrix() if not (r["subject"] == "coronavirus" and r["tagged"])]
    result = adj.adjudicate(rows)
    assert not result.valid
    assert any("missing" in p.lower() and "coronavirus" in p for p in result.problems), result.problems


def test_an_unregistered_subject_makes_the_run_invalid():
    """The pre-registration names three subjects; a fourth is a different study."""
    rows = registered_matrix() + [record("wikipedia", False, 0)]
    result = adj.adjudicate(rows)
    assert not result.valid
    assert any("wikipedia" in p for p in result.problems), result.problems


def test_a_trail_that_is_not_fifteen_presses_makes_the_run_invalid():
    """15 presses is registered; 14 or 16 is a different measurement."""
    rows = registered_matrix()
    rows[0]["focus_trail"] = rows[0]["focus_trail"][:14]
    result = adj.adjudicate(rows)
    assert not result.valid
    assert any("15" in p for p in result.problems), result.problems


def test_a_failed_run_makes_the_matrix_invalid():
    rows = registered_matrix()
    rows[3]["ok"] = False
    rows[3]["error"] = "TimeoutError"
    result = adj.adjudicate(rows)
    assert not result.valid
    assert any("ok" in p.lower() or "fail" in p.lower() for p in result.problems), result.problems


def test_h0_survival_is_not_reported_when_reproducibility_fails():
    """PREREG P1: 'if an arm disagrees with itself ... this run is void'."""
    rows = registered_matrix()
    rows[1]["focus_trail"] = [f"{i}:z" for i in range(15)]  # citiprogram untagged r1
    result = adj.adjudicate(rows)
    assert result.valid, result.problems  # the matrix is complete; P1 is what failed
    assert result.p1 is False
    assert result.verdict.startswith("VOID"), result.verdict
    assert "P1" in result.verdict
    report = "\n".join(result.lines + [result.verdict]).lower()
    assert "not falsified" not in report, report
    assert "survive" not in report, report


def test_h0_survival_is_not_reported_when_the_probe_control_fails():
    """PREREG P3: 'the probe itself is broken and no conclusion ... may be drawn'."""
    flat = ["0:a"] * 15  # a probe returning a constant makes H0 pass trivially
    rows = [r for r in registered_matrix() if r["subject"] == "citiprogram"]
    for s in ("coronavirus", "craigslist"):
        for tagged in (False, True):
            for repeat in (0, 1):
                rows.append(record(s, tagged, repeat, trail=flat))
    result = adj.adjudicate(rows)
    assert result.valid and result.p1
    assert result.p3 is False
    assert result.verdict.startswith("VOID") and "P3" in result.verdict
    assert "not falsified" not in "\n".join(result.lines + [result.verdict]).lower()


def test_a_valid_run_whose_arms_differ_reports_h0_falsified():
    rows = registered_matrix()
    distinct = [f"{i}:a" for i in range(15)]
    for r in rows:
        r["focus_trail"] = list(distinct)
    for r in rows:
        if r["subject"] == "craigslist" and r["tagged"]:
            r["focus_trail"][7] = "7:div"
    result = adj.adjudicate(rows)
    assert result.valid and result.p1 and result.p3
    assert result.p2 is False
    assert "FALSIFIED" in result.verdict and not result.verdict.startswith("VOID")
    assert any("FIRST DIVERGENCE at press 7" in line for line in result.lines), result.lines


def test_a_valid_run_whose_arms_agree_reports_h0_not_falsified():
    rows = registered_matrix()
    distinct = [f"{i}:a" for i in range(15)]
    for r in rows:
        r["focus_trail"] = list(distinct)
    result = adj.adjudicate(rows)
    assert result.valid and result.p1 and result.p2 and result.p3
    assert result.verdict.startswith("H0 NOT FALSIFIED")


def test_comparisons_read_only_the_first_fifteen_presses():
    """Survival is limited to the registered window even if more was recorded."""
    assert adj.presses({"focus_trail": [str(i) for i in range(40)]}) == [
        str(i) for i in range(15)
    ]


def test_a_trail_containing_an_unsupported_scope_marker_makes_the_run_invalid():
    """The probe marks scopes it cannot identify inside (R4); counting them as
    ordinary stops would put a known collision into P2 and P3."""
    from tools import replay

    rows = registered_matrix()
    rows[0]["focus_trail"][3] = "1:body/0:iframe/" + replay.OPAQUE_SCOPE
    result = adj.adjudicate(rows)
    assert not result.valid
    assert any("unsupported" in p.lower() for p in result.problems), result.problems
