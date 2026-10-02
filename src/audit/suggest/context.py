"""Build the small, redacted evidence bundle the model sees for one occurrence.

Everything here is read from the stored scan. Nothing is fetched from the
site. Each field is capped, redacted, and later wrapped as untrusted data in
the prompt: page text, markup, OCR text and URLs come from the scanned site
and can contain instructions aimed at the model.
"""

from __future__ import annotations

import gzip
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from bs4 import BeautifulSoup

from audit.extractor.html_images import image_element_html
from audit.protected.redaction import redact_text, redact_url
from audit.suggest.models import (
    MAX_SNIPPET_CHARS,
    Audience,
    Confidence,
    OccurrenceKind,
)
from audit.web import image_findings_queries, issues

MAX_NEARBY_CHARS = 1500
MAX_FIX_STEPS = 6
MAX_IMAGE_BYTES = 4 * 1024 * 1024
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

# Pipelines whose problem is about how the page looks, so a picture of it
# helps the model. Others are judged from the markup alone, with the
# smaller, faster text model.
_VISUAL_PIPELINES = frozenset({"focus", "visual", "responsive"})
_VISUAL_RULES = frozenset({"color-contrast", "color-contrast-enhanced", "link-in-text-block"})

# Browser checks and the AI review are judgments about behaviour; a fix for
# them is a guess until a person checks it. Rule checks are firmer.
_FIRM_PIPELINES = frozenset({"axe", "alfa", "image"})

# Who-fixes-it values that mean a content editor, not a developer.
_EDITOR_OWNERS = frozenset({"editor", "content"})

# Strip values people typed into form fields. The scan saved the markup as it
# was, which can include a search term or a name in ``value="..."``.
_FORM_VALUE_RE = re.compile(
    r"""(<(?:input|textarea|option)\b[^>]*?\bvalue\s*=\s*)("[^"]*"|'[^']*'|[^\s>]+)""",
    re.IGNORECASE,
)


class OccurrenceNotFoundError(LookupError):
    """The occurrence does not exist in this report."""


class NothingToFixError(ValueError):
    """The occurrence is an old record kept for history, not a problem to fix."""


@dataclass(frozen=True)
class EvidenceBundle:
    scan_id: int
    page_id: int
    occurrence_kind: OccurrenceKind
    occurrence_id: int
    pipeline: str
    rule_id: str
    issue_title: str
    wcag_sc: str | None
    page_url: str
    problem: str
    snippet: str | None
    selector: str | None
    nearby_text: str | None
    fix_steps: tuple[str, ...]
    image_facts: dict[str, str] = field(default_factory=dict)
    image_bytes: bytes | None = None
    audience_default: Audience = "developer"
    confidence: Confidence = "likely"
    # Rule that can be re-run on suggested markup; None when no offline
    # check exists for this kind of problem.
    check_rule_id: str | None = None


def _clip(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


def safe_text(value: Any, limit: int) -> str | None:
    clipped = _clip(value, limit)
    return redact_text(clipped) if clipped is not None else None


def safe_markup(value: Any, limit: int = MAX_SNIPPET_CHARS) -> str | None:
    clipped = _clip(value, limit)
    if clipped is None:
        return None
    return redact_text(_FORM_VALUE_RE.sub(r'\1""', clipped))


def _page_row(conn: sqlite3.Connection, scan_id: int, page_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT id, url_normalized, final_url, rendered_html FROM pages "
        "WHERE id = ? AND scan_id = ?",
        (page_id, scan_id),
    ).fetchone()
    if row is None:
        raise OccurrenceNotFoundError
    return cast("sqlite3.Row", row)


def _nearby_text(rendered: bytes | None, selector: str | None) -> str | None:
    """Visible text around the element, so the model knows what it is for."""
    if not rendered or not selector:
        return None
    try:
        html = gzip.decompress(rendered)
    except (OSError, EOFError):
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    try:
        node = soup.select_one(selector)
    except Exception:  # a scanned selector may be any syntax
        return None
    if node is None:
        return None
    parent = node.parent or node
    text = " ".join(parent.get_text(" ").split())
    return safe_text(text, MAX_NEARBY_CHARS)


def _image_markup(page: sqlite3.Row, position: int, alt: str | None) -> str | None:
    """The image's element code from the saved copy, for the "Before" view.

    The images check stores the image's facts, not its markup, so without
    this an image suggestion had no "Before" to compare the "After" with.
    """
    rendered = page["rendered_html"]
    if not rendered:
        return None
    try:
        body = gzip.decompress(rendered)
    except (OSError, EOFError):
        return None
    base = str(page["final_url"] or page["url_normalized"] or "")
    return safe_markup(image_element_html(body, base, position, alt))


def _blob_bytes(blob_dir: Path, content_hash: str | None) -> bytes | None:
    if not content_hash or not _HASH_RE.match(content_hash):
        return None
    for path in (blob_dir / content_hash[:2]).glob(f"{content_hash}.*"):
        try:
            if path.stat().st_size > MAX_IMAGE_BYTES:
                return None
            return path.read_bytes()
        except OSError:
            return None
    return None


def _first_selector(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.startswith("["):
        # axe stores a JSON list of selectors (frames, shadow roots); the
        # last one is the element itself.
        import json

        try:
            parts = json.loads(text)
        except ValueError:
            return text
        while isinstance(parts, list) and parts:
            parts = parts[-1]
        return str(parts) if parts else None
    return text


def _issue_row_for(
    rows: list[issues.IssueRow], *, finding_id: int | None = None, key: str | None = None
) -> issues.IssueRow | None:
    for row in rows:
        if key is not None and row.issue_key == key:
            return row
        if finding_id is not None and (
            finding_id in row.finding_ids or finding_id in row.repeat_finding_ids
        ):
            return row
    return None


def _audience(row: issues.IssueRow | None) -> Audience:
    owner = (row.responsibility if row else "dev") or "dev"
    return "editor" if owner in _EDITOR_OWNERS else "developer"


def locate(
    conn: sqlite3.Connection,
    *,
    scan_id: int,
    occurrence_kind: OccurrenceKind,
    occurrence_id: int,
) -> tuple[int, Audience]:
    """Check the occurrence is in this report; return its page and audience.

    Cheap enough to run inside the request, so a bad id is refused at once
    rather than failing later in the queue.
    """
    rows = issues.list_issues(conn, scan_id)
    if occurrence_kind == "a11y":
        f = conn.execute(
            "SELECT page_id FROM page_a11y_findings WHERE id = ? AND scan_id = ?",
            (occurrence_id, scan_id),
        ).fetchone()
        if f is None:
            raise OccurrenceNotFoundError
        row = _issue_row_for(rows, finding_id=occurrence_id)
        page_id = int(f["page_id"])
    else:
        page_id, image_id = _image_occurrence_ids(conn, scan_id, occurrence_id)
        key = image_findings_queries.issue_keys_for_images(conn, scan_id, [image_id]).get(image_id)
        if key is None:
            # The scan made no finding for this image, so there is no issue
            # to suggest a fix for.
            raise OccurrenceNotFoundError
        row = _issue_row_for(rows, key=key)
    if row is not None and row.review_lane == "informational":
        raise NothingToFixError
    return page_id, _audience(row)


def _image_occurrence_ids(
    conn: sqlite3.Connection, scan_id: int, occurrence_id: int
) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT pi.page_id, pi.image_id
          FROM page_images pi JOIN pages p ON p.id = pi.page_id
         WHERE pi.id = ? AND p.scan_id = ?
        """,
        (occurrence_id, scan_id),
    ).fetchone()
    if row is None:
        raise OccurrenceNotFoundError
    return int(row["page_id"]), int(row["image_id"])


def image_before_html(conn: sqlite3.Connection, *, scan_id: int, occurrence_id: int) -> str | None:
    """The "Before" code for an image occurrence of this report, or None.

    Suggestions saved before the image element was looked up have no
    "Before"; this fills it in when they are read.
    """
    row = conn.execute(
        """
        SELECT pi.position, pi.alt_text, p.url_normalized, p.final_url, p.rendered_html
          FROM page_images pi JOIN pages p ON p.id = pi.page_id
         WHERE pi.id = ? AND p.scan_id = ?
        """,
        (occurrence_id, scan_id),
    ).fetchone()
    if row is None:
        return None
    return _image_markup(row, int(row["position"]), row["alt_text"])


def build(
    conn: sqlite3.Connection,
    blob_dir: Path,
    *,
    scan_id: int,
    occurrence_kind: OccurrenceKind,
    occurrence_id: int,
) -> EvidenceBundle:
    rows = issues.list_issues(conn, scan_id)
    if occurrence_kind == "a11y":
        return _build_a11y(conn, blob_dir, rows, scan_id, occurrence_id)
    return _build_image(conn, blob_dir, rows, scan_id, occurrence_id)


def _build_a11y(
    conn: sqlite3.Connection,
    blob_dir: Path,
    rows: list[issues.IssueRow],
    scan_id: int,
    finding_id: int,
) -> EvidenceBundle:
    f = conn.execute(
        """
        SELECT id, page_id, pipeline, rule_id, wcag_sc, help, target_selector,
               failure_summary, html_snippet, screenshot_hash
          FROM page_a11y_findings WHERE id = ? AND scan_id = ?
        """,
        (finding_id, scan_id),
    ).fetchone()
    if f is None:
        raise OccurrenceNotFoundError
    page = _page_row(conn, scan_id, int(f["page_id"]))
    row = _issue_row_for(rows, finding_id=finding_id)
    if row is not None and row.review_lane == "informational":
        raise NothingToFixError
    pipeline = str(f["pipeline"] or "axe")
    rule_id = str(f["rule_id"])
    selector = _first_selector(f["target_selector"])
    wants_picture = pipeline in _VISUAL_PIPELINES or rule_id in _VISUAL_RULES
    problem_parts = [p for p in (f["help"], f["failure_summary"]) if p]
    return EvidenceBundle(
        scan_id=scan_id,
        page_id=int(f["page_id"]),
        occurrence_kind="a11y",
        occurrence_id=finding_id,
        pipeline=pipeline,
        rule_id=rule_id,
        issue_title=(row.title if row else rule_id),
        wcag_sc=(row.wcag_sc if row else f["wcag_sc"]),
        page_url=redact_url(str(page["final_url"] or page["url_normalized"])),
        problem=safe_text("\n".join(str(p) for p in problem_parts), 1200) or rule_id,
        snippet=safe_markup(f["html_snippet"]),
        selector=safe_text(selector, 400),
        nearby_text=_nearby_text(page["rendered_html"], selector),
        fix_steps=tuple(
            s for s in (safe_text(x, 400) for x in (row.fix_steps if row else ())) if s
        )[:MAX_FIX_STEPS],
        image_bytes=(_blob_bytes(blob_dir, f["screenshot_hash"]) if wants_picture else None),
        audience_default=_audience(row),
        confidence="likely" if pipeline in _FIRM_PIPELINES else "guess",
        check_rule_id=rule_id if pipeline == "axe" else None,
    )


def _build_image(
    conn: sqlite3.Connection,
    blob_dir: Path,
    rows: list[issues.IssueRow],
    scan_id: int,
    occurrence_id: int,
) -> EvidenceBundle:
    page_id, image_id = _image_occurrence_ids(conn, scan_id, occurrence_id)
    key = image_findings_queries.issue_keys_for_images(conn, scan_id, [image_id]).get(image_id)
    if key is None:
        raise OccurrenceNotFoundError
    occ = conn.execute(
        """
        SELECT pi.alt_text, pi.role, pi.context_snippet, pi.position,
               i.src_url_canonical, i.blob_path,
               a.ocr_text, a.vlm_classification, a.vlm_rationale
          FROM page_images pi
          JOIN images i ON i.id = pi.image_id
          LEFT JOIN analyses a ON a.image_id = i.id
         WHERE pi.id = ?
         ORDER BY a.analyzed_at DESC
         LIMIT 1
        """,
        (occurrence_id,),
    ).fetchone()
    page = _page_row(conn, scan_id, page_id)
    row = _issue_row_for(rows, key=key)
    image_bytes: bytes | None = None
    if occ["blob_path"]:
        path = (blob_dir / str(occ["blob_path"])).resolve()
        if (
            path.is_relative_to(blob_dir.resolve())
            and path.is_file()
            and path.stat().st_size <= MAX_IMAGE_BYTES
        ):
            image_bytes = path.read_bytes()
    alt = occ["alt_text"]
    facts = {
        "Current text alternative (alt)": (
            "(none)" if alt is None else (safe_text(alt, 400) or '""')
        ),
        "Words found in the image (OCR)": safe_text(occ["ocr_text"], 1200) or "(none)",
        "What the image check decided": str(occ["vlm_classification"] or "unknown"),
        "Why it decided that": safe_text(occ["vlm_rationale"], 600) or "(none)",
        "Image address": redact_url(str(occ["src_url_canonical"] or "")),
    }
    if occ["role"]:
        facts["Role"] = str(occ["role"])
    return EvidenceBundle(
        scan_id=scan_id,
        page_id=page_id,
        occurrence_kind="image",
        occurrence_id=occurrence_id,
        pipeline="image",
        rule_id=key,
        issue_title=(row.title if row else key),
        wcag_sc=(row.wcag_sc if row else "1.4.5"),
        page_url=redact_url(str(page["final_url"] or page["url_normalized"])),
        problem=(row.description if row and row.description else "An image may contain text."),
        snippet=_image_markup(page, int(occ["position"]), alt),
        selector=None,
        nearby_text=safe_text(occ["context_snippet"], MAX_NEARBY_CHARS),
        fix_steps=tuple(
            s for s in (safe_text(x, 400) for x in (row.fix_steps if row else ())) if s
        )[:MAX_FIX_STEPS],
        image_facts=facts,
        image_bytes=image_bytes,
        audience_default=_audience(row) if row else "editor",
        confidence="likely",
        check_rule_id=None,
    )
