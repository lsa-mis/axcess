"""Every image in one report, for the report's Images tab.

The Issues tab lists image *issue types*; the image findings it draws on
(``findings``) exist only for images the scan found text in. The Images tab
answers a different question, "which images need alt text work?", so it
lists every image the scan saw on a page, including images with no text in
them, which have no finding.

Each image is in up to two of three groups. A group is a question a person
asks of the list, not a category the image belongs to:

* ``with_text``: the scan read text in the image (OCR, or text drawn in an
  inline SVG).
* ``missing_alt``: at least one place it appears has no alt attribute.
* ``with_alt``: every place it appears has an alt attribute (``alt=""``
  included: the author marked it decorative).

The last two never overlap; ``with_text`` overlaps both.

Each image also gets one verdict on its alt text, from the most direct
evidence there is:

* ``needs_alt`` from the page code: an ``<img>`` with no alt attribute, or
  an empty alt on an image the scan read text in (that hides the text).
* ``good`` or ``needs_better`` from the text match in
  :mod:`audit.synthesizer.alt_compare`, for an image with text.
* ``good`` or ``needs_better`` from the local model, for an image with no
  text that a person asked the model to check (``alt_text_checks``).
* ``not_checked`` otherwise. The text match cannot judge an image with no
  text in it, and saying "adequate" there (what ``alt_compare`` returns,
  because it has nothing to compare) would claim a check that did not run.

Everything here reads one ``scan_id``. Queries join through ``pages`` for
the scan, so an image another report also saw is never counted twice and a
check saved for one report is never shown in another.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from audit.synthesizer.alt_compare import AltAdequacy, compare, worst

ImageGroup = Literal["with_text", "missing_alt", "with_alt"]
Verdict = Literal["good", "needs_better", "needs_alt", "not_checked"]
VerdictSource = Literal["page_code", "text_match", "local_model"]

GROUPS: tuple[ImageGroup, ...] = ("with_text", "missing_alt", "with_alt")
VERDICTS: tuple[Verdict, ...] = ("needs_alt", "needs_better", "not_checked", "good")

# The list is worked through worst first: images that need alt text, then
# those whose alt text needs work, then those nobody has judged yet.
_VERDICT_ORDER = {verdict: index for index, verdict in enumerate(VERDICTS)}

MAX_LIMIT = 50
# Lengths sent to the browser. Long OCR text or alt text is evidence, but a
# table cell needs a sentence, not a page; the full text stays in the DB.
TEXT_LIMIT = 300

_REASON_MISSING = "Alt text is missing."
_REASON_EMPTY_WITH_TEXT = "Empty alt text hides the text in the image."
_REASON_MATCH = "Matches the text in the image."
_REASON_PARTIAL = "Only partly matches the text in the image."
_REASON_NO_MATCH = "Does not match the text in the image."
_REASON_DECORATIVE = "Marked decorative (empty alt text). Check that the image adds nothing."
_REASON_NOT_CHECKED = "No text in the image to compare."


class GroupCounts(BaseModel):
    """How many images a group holds, and how many have each verdict."""

    total: int = 0
    good: int = 0
    needs_better: int = 0
    needs_alt: int = 0
    not_checked: int = 0


class ReportImage(BaseModel):
    """One image of one report, as a row of the Images tab."""

    image_id: int
    content_hash: str
    mime: str | None
    image_url: str
    has_svg_text: bool
    groups: list[ImageGroup]
    page_count: int
    sample_page_id: int | None
    sample_page_url: str | None
    # The alt text a reader meets first among the worst occurrences: None is
    # no alt attribute, "" is alt="".
    alt_text: str | None
    # How many different alt texts the image has across its pages.
    alt_text_variants: int
    has_text: bool
    image_text: str | None
    verdict: Verdict
    verdict_source: VerdictSource | None
    verdict_reason: str
    suggestion: str | None
    suggestion_model: str | None
    # Whether the local model can look at this image at all: it needs the
    # saved picture, and an inline SVG has none.
    can_check: bool
    finding_id: int | None


class ReportImagesResponse(BaseModel):
    """One page of the Images tab."""

    scan_id: int
    group: ImageGroup
    verdict: Verdict | None
    q: str
    counts: dict[ImageGroup, GroupCounts]
    total: int
    limit: int
    offset: int
    rows: list[ReportImage]
    # Whether a local model is set up to check alt text and suggest some.
    check_available: bool


@dataclass(frozen=True)
class CheckTarget:
    """What the local model needs to check one image's alt text."""

    image_id: int
    blob_path: str | None
    mime: str | None
    has_svg_text: bool
    alt_text: str | None
    image_text: str
    context_snippet: str | None

    @property
    def can_check(self) -> bool:
        return _can_check(self.blob_path, self.mime)


def _can_check(blob_path: str | None, mime: str | None) -> bool:
    return bool(blob_path) and not (mime or "").startswith("image/svg")


def _clip(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    if len(collapsed) <= TEXT_LIMIT:
        return collapsed
    return collapsed[: TEXT_LIMIT - 1].rstrip() + "…"


def _scan_images(conn: sqlite3.Connection, scan_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH scan_images AS (
            SELECT DISTINCT pi.image_id
              FROM page_images pi
              JOIN pages p ON p.id = pi.page_id
             WHERE p.scan_id = ?
        ),
        best AS (
            SELECT a.image_id, a.ocr_text, a.has_text,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.image_id
                       ORDER BY
                           CASE WHEN a.vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                           a.analyzed_at DESC,
                           a.id DESC
                   ) AS rank
              FROM analyses a
             WHERE a.image_id IN (SELECT image_id FROM scan_images)
        )
        SELECT i.id, i.content_hash, i.mime, i.src_url_canonical, i.has_svg_text,
               i.blob_path, b.ocr_text, b.has_text
          FROM images i
          JOIN scan_images s ON s.image_id = i.id
          LEFT JOIN best b ON b.image_id = i.id AND b.rank = 1
        """,
        (scan_id,),
    ).fetchall()


def _scan_occurrences(
    conn: sqlite3.Connection, scan_id: int, image_id: int | None = None
) -> dict[int, list[dict[str, Any]]]:
    clause = " AND pi.image_id = ?" if image_id is not None else ""
    params: tuple[Any, ...] = (scan_id, image_id) if image_id is not None else (scan_id,)
    rows = conn.execute(
        f"""
        SELECT pi.image_id, pi.page_id, pi.alt_text, pi.context_snippet,
               p.url_normalized AS page_url
          FROM page_images pi
          JOIN pages p ON p.id = pi.page_id
         WHERE p.scan_id = ?{clause}
         ORDER BY pi.image_id, p.id, pi.position
        """,  # noqa: S608, the clause is a fixed string with a placeholder
        params,
    ).fetchall()
    by_image: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_image.setdefault(int(r["image_id"]), []).append(dict(r))
    return by_image


def _scan_checks(conn: sqlite3.Connection, scan_id: int) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        "SELECT image_id, verdict, reason, suggestion, model"
        " FROM alt_text_checks WHERE scan_id = ?",
        (scan_id,),
    ).fetchall()
    return {int(r["image_id"]): r for r in rows}


def _scan_finding_ids(conn: sqlite3.Connection, scan_id: int) -> dict[int, int]:
    rows = conn.execute(
        "SELECT image_id, MIN(id) AS id FROM findings WHERE scan_id = ? GROUP BY image_id",
        (scan_id,),
    ).fetchall()
    return {int(r["image_id"]): int(r["id"]) for r in rows}


def _visible_text(
    ocr_text: str | None, has_svg_text: bool, occurrences: list[dict[str, Any]]
) -> str:
    """The text the scan read in the image, as the synthesizer reads it."""
    text = ocr_text or ""
    if not text and has_svg_text and occurrences:
        text = occurrences[0].get("context_snippet") or ""
    return text


def judge(
    *,
    has_text: bool,
    visible_text: str,
    alts: list[str | None],
    check: sqlite3.Row | dict[str, Any] | None,
) -> tuple[Verdict, VerdictSource | None, str, str | None]:
    """Return ``(verdict, source, reason, alt_text_shown)`` for one image.

    ``alts`` holds the alt attribute of each place the image appears.
    """
    if not alts or any(alt is None for alt in alts):
        return "needs_alt", "page_code", _REASON_MISSING, None
    empty = [alt for alt in alts if alt is not None and not alt.strip()]
    if has_text:
        if empty:
            return "needs_alt", "page_code", _REASON_EMPTY_WITH_TEXT, ""
        buckets = [compare(alt, visible_text) for alt in alts]
        bucket = worst(buckets)
        shown = alts[buckets.index(bucket)]
        if bucket is AltAdequacy.ADEQUATE:
            return "good", "text_match", _REASON_MATCH, shown
        if bucket is AltAdequacy.PARTIAL:
            return "needs_better", "text_match", _REASON_PARTIAL, shown
        return "needs_better", "text_match", _REASON_NO_MATCH, shown
    shown = alts[0]
    if check is not None and check["verdict"] in ("good", "needs_better"):
        return check["verdict"], "local_model", str(check["reason"] or ""), shown
    if empty and len(empty) == len(alts):
        return "not_checked", None, _REASON_DECORATIVE, ""
    return "not_checked", None, _REASON_NOT_CHECKED, shown


def _build_rows(conn: sqlite3.Connection, scan_id: int) -> list[ReportImage]:
    occurrences = _scan_occurrences(conn, scan_id)
    checks = _scan_checks(conn, scan_id)
    findings = _scan_finding_ids(conn, scan_id)
    rows: list[ReportImage] = []
    for r in _scan_images(conn, scan_id):
        image_id = int(r["id"])
        occs = occurrences.get(image_id, [])
        has_svg_text = bool(r["has_svg_text"])
        has_text = has_svg_text or bool(r["has_text"])
        alts = [occ["alt_text"] for occ in occs]
        visible = _visible_text(r["ocr_text"], has_svg_text, occs)
        check = checks.get(image_id)
        verdict, source, reason, shown = judge(
            has_text=has_text, visible_text=visible, alts=alts, check=check
        )
        missing = any(alt is None for alt in alts)
        groups: list[ImageGroup] = []
        if has_text:
            groups.append("with_text")
        groups.append("missing_alt" if missing else "with_alt")
        page_ids = list(dict.fromkeys(int(occ["page_id"]) for occ in occs))
        rows.append(
            ReportImage(
                image_id=image_id,
                content_hash=str(r["content_hash"]),
                mime=r["mime"],
                image_url=str(r["src_url_canonical"]),
                has_svg_text=has_svg_text,
                groups=groups,
                page_count=len(page_ids),
                sample_page_id=int(occs[0]["page_id"]) if occs else None,
                sample_page_url=str(occs[0]["page_url"]) if occs else None,
                alt_text=_clip(shown),
                alt_text_variants=len(set(alts)),
                has_text=has_text,
                image_text=_clip(visible) or None,
                verdict=verdict,
                verdict_source=source,
                verdict_reason=reason,
                suggestion=_clip(check["suggestion"])
                if check is not None and check["suggestion"]
                else None,
                suggestion_model=str(check["model"]) if check is not None else None,
                can_check=_can_check(r["blob_path"], r["mime"]),
                finding_id=findings.get(image_id),
            )
        )
    return rows


def _matches(row: ReportImage, q: str) -> bool:
    needle = q.casefold()
    return any(
        needle in (value or "").casefold()
        for value in (row.alt_text, row.image_text, row.sample_page_url, row.suggestion)
    )


def list_report_images(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    group: ImageGroup = "with_text",
    verdict: Verdict | None = None,
    q: str = "",
    limit: int = 25,
    offset: int = 0,
    check_available: bool = False,
) -> ReportImagesResponse:
    """One page of one group of the report's images, worst first.

    ``limit`` is capped at :data:`MAX_LIMIT`. The counts are for the whole
    report, before the verdict filter and the search, so the group buttons
    keep their numbers while the table narrows.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    rows = _build_rows(conn, scan_id)

    counts: dict[ImageGroup, GroupCounts] = {g: GroupCounts() for g in GROUPS}
    for row in rows:
        for g in row.groups:
            c = counts[g]
            c.total += 1
            setattr(c, row.verdict, getattr(c, row.verdict) + 1)

    q = q.strip()[:200]
    chosen = [
        row
        for row in rows
        if group in row.groups
        and (verdict is None or row.verdict == verdict)
        and (not q or _matches(row, q))
    ]
    chosen.sort(key=lambda row: (_VERDICT_ORDER[row.verdict], -row.page_count, row.image_id))
    return ReportImagesResponse(
        scan_id=scan_id,
        group=group,
        verdict=verdict,
        q=q,
        counts=counts,
        total=len(chosen),
        limit=limit,
        offset=offset,
        rows=chosen[offset : offset + limit],
        check_available=check_available,
    )


def all_report_images(conn: sqlite3.Connection, scan_id: int) -> list[ReportImage]:
    """Every image of the report, worst verdict first, for the ZIP export."""
    rows = _build_rows(conn, scan_id)
    rows.sort(key=lambda row: (_VERDICT_ORDER[row.verdict], -row.page_count, row.image_id))
    return rows


def get_report_image(conn: sqlite3.Connection, scan_id: int, image_id: int) -> ReportImage | None:
    """One image's row, or None when the image is not on a page of this scan."""
    for row in _build_rows(conn, scan_id):
        if row.image_id == image_id:
            return row
    return None


def check_target(conn: sqlite3.Connection, scan_id: int, image_id: int) -> CheckTarget | None:
    """The image as the model should see it, or None when it is not in this scan."""
    occs = _scan_occurrences(conn, scan_id, image_id).get(image_id)
    if not occs:
        return None
    image = conn.execute(
        "SELECT id, blob_path, mime, has_svg_text FROM images WHERE id = ?", (image_id,)
    ).fetchone()
    if image is None:
        return None
    analysis = conn.execute(
        """
        SELECT ocr_text FROM analyses WHERE image_id = ?
         ORDER BY CASE WHEN vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                  analyzed_at DESC, id DESC
         LIMIT 1
        """,
        (image_id,),
    ).fetchone()
    alts = [occ["alt_text"] for occ in occs]
    # The alt text a reader is most likely to meet: the first non-empty one.
    alt = next((a for a in alts if a), None if any(a is None for a in alts) else "")
    snippet = next((occ["context_snippet"] for occ in occs if occ["context_snippet"]), None)
    return CheckTarget(
        image_id=image_id,
        blob_path=image["blob_path"],
        mime=image["mime"],
        has_svg_text=bool(image["has_svg_text"]),
        alt_text=alt,
        image_text=_visible_text(
            analysis["ocr_text"] if analysis is not None else None,
            bool(image["has_svg_text"]),
            occs,
        ),
        context_snippet=snippet,
    )


def save_check(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    image_id: int,
    verdict: Literal["good", "needs_better"] | None,
    reason: str,
    suggestion: str,
    model: str,
    prompt_version: str,
) -> None:
    """Keep the model's answer for this image in this report, replacing any earlier one."""
    conn.execute(
        """
        INSERT INTO alt_text_checks
            (scan_id, image_id, verdict, reason, suggestion, model, prompt_version)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id, image_id) DO UPDATE SET
            verdict = excluded.verdict,
            reason = excluded.reason,
            suggestion = excluded.suggestion,
            model = excluded.model,
            prompt_version = excluded.prompt_version,
            created_at = CURRENT_TIMESTAMP
        """,
        (scan_id, image_id, verdict, reason, suggestion, model, prompt_version),
    )
