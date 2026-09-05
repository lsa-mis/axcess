"""DOM-state (click-through) coverage, projected once for every export.

Five export formats and the stakeholder report all need to answer the same
question about the interaction probe, so they read it from here rather than
each re-joining the tables and drifting apart, the same reason
``coverage_matrix`` is the single source of truth for WCAG claims and
``web.issues`` for the unified issue view.

The auditor's question is not "how many states." It is:

* **Coverage**, of the controls this page exposes, which were operated, and
  what stopped the rest?  (``scan_interaction_runs``)
* **Provenance**, for this finding, what had to be clicked to see it?
  (``page_a11y_findings.revealed_by``)
* **Reproduction**, how does a developer get back to it?  (:func:`reproduction_step`)

Three states are deliberately distinguishable and must never collapse into one
number: the probe was **off**, the probe **ran and found nothing**, and the
ledger was **not recorded** because the scan predates it. A zero that means
"not recorded" would be read as "nothing to click," which is a coverage claim
the data does not support.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

# Bounds the probe reports in ``scan_interaction_runs.limits``, mapped to
# language a non-technical reader can act on. The probe stops deliberately;
# a stop is a coverage fact, not an error.
LIMIT_LABELS: dict[str, str] = {
    "clicks": "reached the per-page click limit",
    "time": "reached the per-page time limit",
    "depth": "reached the nesting limit for newly revealed controls",
    "repeated_controls": "sampled only some of a repeated control",
    "dialog_not_dismissed": "stopped early because a dialog would not close",
}


# Every column the projection reads. A ledger missing any of them cannot
# support the operated-vs-found statement this module exists to make.
_LEDGER_COLUMNS = frozenset(
    {
        "page_id",
        "controls_found",
        "controls_operated",
        "clicks_attempted",
        "clicks_succeeded",
        "states",
        "blocked_controls",
        "dialogs_opened",
        "dialogs_stuck",
        "limits",
        "detail",
    }
)


@dataclass(frozen=True)
class PageInteraction:
    """One page's click-through ledger row."""

    page_id: int
    page_url: str
    page_title: str | None
    controls_found: int
    controls_operated: int
    clicks_attempted: int
    clicks_succeeded: int
    states: int
    blocked_controls: int
    dialogs_opened: int
    dialogs_stuck: int
    limits: tuple[str, ...] = ()
    detail: str = ""

    @property
    def was_limited(self) -> bool:
        return bool(self.limits)

    @property
    def limit_text(self) -> str:
        """Plain-language reason(s) the sweep stopped, or an empty string."""
        return "; ".join(LIMIT_LABELS.get(x, x) for x in self.limits)

    @property
    def coverage_ratio(self) -> float | None:
        """Operated / found, or ``None`` when the page exposed no controls.

        ``None`` is not zero: a page with nothing to click is fully covered
        by the load-state pass, not badly covered by the probe.
        """
        if self.controls_found <= 0:
            return None
        return self.controls_operated / self.controls_found


@dataclass(frozen=True)
class InteractionCoverage:
    """Scan-level click-through coverage, plus the per-page ledger."""

    enabled: bool
    # False for scans written before the ledger existed. Their totals may
    # still be present, but per-page coverage must be reported as unrecorded.
    ledger_recorded: bool
    pages_probed: int
    states_total: int
    controls_found: int
    controls_operated: int
    blocked_controls: int
    dialogs_stuck: int
    findings_revealed: int
    pages: list[PageInteraction] = field(default_factory=list)

    @property
    def limited_pages(self) -> list[PageInteraction]:
        """Pages where a bound stopped the sweep, the "not fully checked" list."""
        return [p for p in self.pages if p.was_limited]

    @property
    def coverage_ratio(self) -> float | None:
        if self.controls_found <= 0:
            return None
        return self.controls_operated / self.controls_found

    @property
    def status_line(self) -> str:
        """One sentence stating what the probe did, safe for any audience."""
        if not self.enabled:
            return (
                "Click-through DOM state discovery was turned off for this scan, "
                "so content that appears only after operating a control was not tested."
            )
        if not self.ledger_recorded:
            return (
                f"Click-through DOM state discovery reached {self.states_total} state(s) "
                f"across {self.pages_probed} page(s). Per-page control coverage was not "
                "recorded for this scan, so the share of controls operated is unknown."
            )
        if self.controls_found == 0:
            return (
                f"Click-through DOM state discovery ran on {self.pages_probed} page(s) "
                "and found no operable controls, so there were no additional states to test."
            )
        return (
            f"Click-through DOM state discovery operated {self.controls_operated} of "
            f"{self.controls_found} control(s) across {self.pages_probed} page(s), "
            f"reaching {self.states_total} additional DOM state(s) that a page load "
            f"alone does not show. {self.findings_revealed} finding(s) in this report "
            "were visible only after a control was operated."
        )

    @property
    def caveats(self) -> list[str]:
        """Honest limits a reader must see next to the numbers above."""
        out: list[str] = []
        if not self.enabled:
            return out
        if self.limited_pages:
            out.append(
                f"{len(self.limited_pages)} page(s) hit a bound before every control was "
                "operated, so their states are partially tested. They are listed below."
            )
        if self.blocked_controls:
            out.append(
                f"{self.blocked_controls} control(s) were deliberately refused because their "
                "labels matched destructive actions such as sign out, delete, or unsubscribe. "
                "Those states require manual testing."
            )
        if self.dialogs_stuck:
            out.append(
                f"{self.dialogs_stuck} dialog(s) did not close again, which ends the sweep for "
                "that page because the overlay covers the remaining controls."
            )
        out.append(
            "Hover-only content, gestures, operating-system menus, closed shadow DOM, "
            "cross-origin embeds, and states with no observable DOM change are outside "
            "what this probe can reach and still require manual testing."
        )
        # Stated wherever DOM-state numbers appear: the rescan comparison comes
        # from the image pipeline only, so a click-revealed barrier missing from
        # a later scan is not evidence that anyone fixed it.
        out.append(
            "Click-revealed findings are not yet compared across scans. If one is absent "
            "from a later report, confirm the fix directly, absence is not proof of repair."
        )
        return out


def reproduction_step(revealed_by: str | None) -> str:
    """How a developer gets back to this finding, in one imperative sentence."""
    if not revealed_by:
        return "Load the page."
    return f'Load the page, then activate "{revealed_by}".'


def load(conn: sqlite3.Connection, scan_id: int) -> InteractionCoverage:
    """Project one scan's click-through coverage from the stored evidence."""
    scan = conn.execute(
        "SELECT config_json, interaction_pages_probed, interaction_states_total "
        "FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if scan is None:
        raise ValueError(f"Scan {scan_id} not found")

    enabled = True
    coverage_version = 0
    try:
        cfg = json.loads(scan["config_json"] or "{}")
        if isinstance(cfg, dict):
            enabled = bool(cfg.get("interaction_checks_enabled", True))
            coverage_version = int(cfg.get("interaction_coverage_version", 0) or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    findings_revealed = int(
        conn.execute(
            "SELECT COUNT(*) FROM page_a11y_findings "
            "WHERE scan_id = ? AND revealed_by IS NOT NULL AND revealed_by != ''",
            (scan_id,),
        ).fetchone()[0]
        or 0
    )

    # The ledger table grew columns after the first scans were written, and
    # those scans already carry coverage_version 2, so the version alone is
    # not a safe gate and a bare SELECT would raise on a real user's older
    # database. Check the columns that are actually present.
    #
    # Partial is treated as absent on purpose. Defaulting a missing
    # ``controls_operated`` to 0 would render "0 of 10 controls operated",
    # which is a false coverage claim; "not recorded" is the true one.
    present = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(scan_interaction_runs)").fetchall()
    }
    has_ledger = present >= _LEDGER_COLUMNS
    pages: list[PageInteraction] = []
    if has_ledger and coverage_version >= 2:
        rows = conn.execute(
            """
            SELECT r.page_id, r.controls_found, r.controls_operated,
                   r.clicks_attempted, r.clicks_succeeded, r.states,
                   r.blocked_controls, r.dialogs_opened, r.dialogs_stuck,
                   r.limits, r.detail,
                   p.url_normalized AS page_url, p.title AS page_title
              FROM scan_interaction_runs r
              JOIN pages p ON p.id = r.page_id
             WHERE r.scan_id = ?
             ORDER BY p.url_normalized
            """,
            (scan_id,),
        ).fetchall()
        for r in rows:
            pages.append(
                PageInteraction(
                    page_id=int(r["page_id"]),
                    page_url=str(r["page_url"]),
                    page_title=r["page_title"],
                    controls_found=int(r["controls_found"] or 0),
                    controls_operated=int(r["controls_operated"] or 0),
                    clicks_attempted=int(r["clicks_attempted"] or 0),
                    clicks_succeeded=int(r["clicks_succeeded"] or 0),
                    states=int(r["states"] or 0),
                    blocked_controls=int(r["blocked_controls"] or 0),
                    dialogs_opened=int(r["dialogs_opened"] or 0),
                    dialogs_stuck=int(r["dialogs_stuck"] or 0),
                    limits=tuple(x for x in str(r["limits"] or "").split(",") if x),
                    detail=str(r["detail"] or ""),
                )
            )

    return InteractionCoverage(
        enabled=enabled,
        ledger_recorded=bool(pages) or (has_ledger and coverage_version >= 2),
        pages_probed=int(scan["interaction_pages_probed"] or 0),
        states_total=int(scan["interaction_states_total"] or 0),
        controls_found=sum(p.controls_found for p in pages),
        controls_operated=sum(p.controls_operated for p in pages),
        blocked_controls=sum(p.blocked_controls for p in pages),
        dialogs_stuck=sum(p.dialogs_stuck for p in pages),
        findings_revealed=findings_revealed,
        pages=pages,
    )
