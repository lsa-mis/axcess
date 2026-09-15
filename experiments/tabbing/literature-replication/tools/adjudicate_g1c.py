"""Adjudicate PREREGISTRATION-G1c against derived/feasibility.json.

Reports every registered prediction, pass or fail, and leads with any
falsification. Nothing here decides anything the pre-registration did not
already fix in advance.

The disposition is validity-gated (gate-2 finding R3). The pre-registration says
a run whose arms disagree with themselves (P1) or whose probe fails its control
(P3) is void and supports no conclusion about H0, so a void run cannot report
H0 survival here either. Records are validated against the registered matrix
before anything is compared, because a missing, duplicated or short record makes
the comparison something other than the one that was registered.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass, field

from tools.replay import OPAQUE_SCOPE

REGISTERED_SUBJECTS = ("citiprogram", "coronavirus", "craigslist")
REGISTERED_ARMS = (False, True)
REGISTERED_REPEATS = (0, 1)
TAB_PRESSES = 15


@dataclass
class Disposition:
    problems: list[str] = field(default_factory=list)
    p1: bool = False
    p2: bool = False
    p3: bool = False
    verdict: str = ""
    lines: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems


def index_records(rows: list[dict]) -> tuple[dict, list[str]]:
    """Index by (subject, arm, repeat), reporting collisions instead of hiding them."""
    by: dict[tuple, dict] = {}
    problems: list[str] = []
    for r in rows:
        key = (r.get("subject"), bool(r.get("tagged")), r.get("repeat"))
        if key in by:
            problems.append(
                f"duplicate record for subject={key[0]} tagged={int(key[1])} "
                f"repeat={key[2]}; the registered matrix has one run per cell"
            )
        by[key] = r
    return by, problems


def validate_matrix(rows: list[dict]) -> tuple[dict, list[str]]:
    by, problems = index_records(rows)
    registered = {
        (s, a, r)
        for s in REGISTERED_SUBJECTS
        for a in REGISTERED_ARMS
        for r in REGISTERED_REPEATS
    }
    for key in sorted(registered - set(by), key=str):
        problems.append(
            f"missing record for subject={key[0]} tagged={int(key[1])} repeat={key[2]}"
        )
    for key in sorted(set(by) - registered, key=str):
        problems.append(
            f"unregistered record subject={key[0]} tagged={key[1]} repeat={key[2]}; "
            "the pre-registration fixes the matrix in advance"
        )
    for key in sorted(set(by) & registered, key=str):
        r = by[key]
        where = f"subject={key[0]} tagged={int(key[1])} repeat={key[2]}"
        if not r.get("ok"):
            problems.append(f"{where}: run did not complete ok ({r.get('error')})")
        trail = r.get("focus_trail")
        if not isinstance(trail, list) or len(trail) != TAB_PRESSES:
            n = len(trail) if isinstance(trail, list) else "no"
            problems.append(f"{where}: {n} focus steps, registered exactly {TAB_PRESSES}")
        for i, stop in enumerate(trail or []):
            if isinstance(stop, str) and OPAQUE_SCOPE in stop:
                problems.append(
                    f"{where}: press {i} landed in an unsupported scope ({stop}); "
                    "its identity is known to collide and cannot be adjudicated"
                )
    return by, problems


def presses(record: dict) -> list[str]:
    """The registered window: the first 15 presses, whatever else was recorded."""
    return list(record.get("focus_trail") or [])[:TAB_PRESSES]


def adjudicate(rows: list[dict]) -> Disposition:
    """One validity-gated disposition over the registered matrix."""
    by, problems = validate_matrix(rows)
    result = Disposition(problems=problems)
    if problems:
        result.lines.append(
            f"matrix invalid: {len(problems)} problem(s); no prediction adjudicated"
        )
        result.verdict = (
            "VOID -- the recorded runs are not the registered matrix; "
            "P1, P2 and P3 are not adjudicated"
        )
        return result

    result.lines.append("P1  within-arm reproducibility (predicted: trails identical)")
    result.p1 = True
    for s in REGISTERED_SUBJECTS:
        for tagged in REGISTERED_ARMS:
            a, b = presses(by[(s, tagged, 0)]), presses(by[(s, tagged, 1)])
            ok = a == b
            result.p1 &= ok
            result.lines.append(f"  {s:<13} tagged={int(tagged)}  identical={ok}")

    result.lines.append("P3  probe discrimination (control: untagged distinct stops > 1 on >=2/3)")
    discriminating = 0
    for s in REGISTERED_SUBJECTS:
        n = len(set(presses(by[(s, False, 0)])))
        discriminating += n > 1
        result.lines.append(f"  {s:<13} untagged distinct stops = {n}")
    result.p3 = discriminating >= 2
    result.lines.append(f"  subjects discriminating: {discriminating}/3")

    # P2 is only meaningful if the run is interpretable at all. The
    # pre-registration voids the run on a P1 or P3 failure, so the comparison is
    # withheld rather than computed and printed beside a void notice.
    if not (result.p1 and result.p3):
        failed = [n for n, ok in (("P1", result.p1), ("P3", result.p3)) if not ok]
        result.lines.append("P2  withheld: the run is void, H0 is not adjudicated")
        result.verdict = (
            f"VOID -- {' and '.join(failed)} failed; "
            "the pre-registration draws no conclusion about H0 from this run"
        )
        return result

    result.lines.append("P2  between-arm equality  ** THE TEST **  (H0: tagged == untagged)")
    result.p2 = True
    for s in REGISTERED_SUBJECTS:
        u, t = presses(by[(s, False, 0)]), presses(by[(s, True, 0)])
        ok = u == t
        result.p2 &= ok
        result.lines.append(
            f"  {s:<13} identical={ok}   stops untagged={len(set(u))} tagged={len(set(t))}"
        )
        if not ok:
            for i, (x, y) in enumerate(zip(u, t)):
                if x != y:
                    result.lines.append(f"      FIRST DIVERGENCE at press {i}: {x!r} != {y!r}")
                    break
    result.verdict = (
        "H0 NOT FALSIFIED -- tagged and untagged trails identical on all three subjects"
        if result.p2
        else "H0 FALSIFIED -- tagged and untagged trails differ; the census is rejected "
        "for focus-dependent measurement and the scored arm stops"
    )
    return result


def main() -> int:
    rows = json.loads(pathlib.Path("derived/feasibility.json").read_text())
    result = adjudicate(rows)

    print("=" * 68)
    print("PREREGISTRATION-G1c adjudication (validity-gated)")
    print("=" * 68)
    for problem in result.problems:
        print(f"  INVALID: {problem}")
    if result.problems:
        print()
    for line in result.lines:
        print(line)

    print()
    print("=" * 68)
    print(f"DISPOSITION: {result.verdict}")
    print("=" * 68)

    old = json.loads(pathlib.Path("derived/feasibility.pre-focus-fix.json").read_text())
    oldby = {(r["subject"], r["tagged"], r["repeat"]): r for r in old}
    by, _ = index_records(rows)
    print()
    print("Superseded vs current distinct-stop counts (untagged arm, first 15 presses):")
    for s in REGISTERED_SUBJECTS:
        o = oldby.get((s, False, 0), {}).get("distinct_focus_stops")
        cur = by.get((s, False, 0))
        n = len(set(presses(cur))) if cur else None
        print(f"  {s:<13} was {o}  ->  now {n}")

    sample = by.get(("craigslist", False, 0))
    if sample:
        print()
        print("Sample trail (craigslist, untagged, first 4 presses):")
        for x in presses(sample)[:4]:
            print(f"  {x}")

    # Non-zero unless the run is valid and H0 survived, so a void or falsified
    # run cannot be mistaken for a pass by anything that reads the exit code.
    return 0 if (result.valid and result.p2) else 1


if __name__ == "__main__":
    sys.exit(main())
