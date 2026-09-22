"""`terminal_period`: the pure half of the cap diagnosis.

Every "focus trap" verdict in `derived/kafe_matrix_capdiag.json` rests on this
function, so the two ways it can lie — calling a trap on a walk that is still
reaching new controls, and missing a trap that is plainly there — are both
pinned here. The browser half is covered by the two controls in
`CAPDIAG-REPORT.md`, which a unit test cannot stand in for.
"""

from tools.kafe_matrix import (
    LOOP_MAX_PERIOD,
    LOOP_MIN_REPEATS,
    LOOP_TAIL,
    terminal_period,
)


def test_a_walk_that_never_repeats_has_no_period():
    assert terminal_period([f"#el:a:{i}" for i in range(4000)]) is None


def test_a_two_element_loop_is_found():
    # What `spotify` does: eight ordinary stops, then focus ping-pongs forever.
    walk = [f"#el:a:{i}" for i in range(8)] + ["#el:iframe:79", "#el:body:15"] * 2000
    assert terminal_period(walk) == 2


def test_the_period_reported_is_the_shortest_one():
    # A 1-element loop also satisfies period 2, 3, ...; the shortest is the fact.
    assert terminal_period(["#el:body:15"] * 300) == 1


def test_a_loop_the_walk_has_left_is_not_terminal():
    # Focus looped early and then escaped. Reporting a trap here would be wrong:
    # the cap came from somewhere else.
    walk = ["a", "b"] * 100 + [f"#el:a:{i}" for i in range(LOOP_TAIL)]
    assert terminal_period(walk) is None


def test_a_short_bounce_needs_the_whole_short_window():
    # Two laps of a 2-cycle at the very end is not enough; `LOOP_TAIL` presses
    # of it is. This is the guard against calling a trap the moment focus
    # happens to revisit one position.
    assert terminal_period([f"#el:a:{i}" for i in range(400)] + ["x", "y"] * 2) is None
    assert terminal_period([f"#el:a:{i}" for i in range(400)] + ["x", "y"] * 40) == 2


def test_an_orbit_longer_than_the_short_window_is_still_found():
    # The `raise` case. A fixed 60-press window called this "no loop" and the
    # verdict then guessed that a larger budget would finish the walk.
    orbit = [f"#el:a:{i}" for i in range(82)]
    assert terminal_period(orbit * LOOP_MIN_REPEATS) == 82


def test_an_orbit_seen_fewer_than_the_required_times_is_not_claimed():
    orbit = [f"#el:a:{i}" for i in range(82)]
    assert terminal_period(orbit * (LOOP_MIN_REPEATS - 1)) is None


def test_a_period_past_the_ceiling_is_not_claimed():
    orbit = [f"#el:a:{i}" for i in range(LOOP_MAX_PERIOD + 1)]
    assert terminal_period(orbit * LOOP_MIN_REPEATS) is None
