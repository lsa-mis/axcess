"""Single source of truth for the coverage & feature tracker.

Both the ``/tracking`` page and ``docs/coverage-tracker.md`` describe the
same thing: which WCAG criteria the tool actually detects today versus
what's planned. To stop those two from drifting, the *structured* status
lives here and the page renders from it. When a roadmap item ships, flip
its ``status`` here and both the page and any generated summary update.

Status values are deliberately few:

* ``"shipped"``  — a wired pipeline persists findings for this (verify in
  the registry / probe modules).
* ``"in_progress"`` — code exists but isn't wired end-to-end yet.
* ``"planned"`` — designed, not started. ``note`` explains any nuance
  (e.g. "configured in default criteria but no analyzer class").

Keep this honest: an accessibility tool that *claims* coverage it doesn't
have is worse than one that's upfront about the gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ShippedPipeline:
    """A detection pipeline that runs on a default crawl today."""

    name: str
    pipeline: str  # the ``page_a11y_findings.pipeline`` discriminator
    engine: str
    scs: str  # human-readable SC coverage
    needs_ai: bool
    note: str = ""


@dataclass(frozen=True)
class RoadmapItem:
    """A planned / in-progress AI analyzer, keyed by WCAG criterion."""

    wcag: str
    issue: str
    ai_fit: str
    model_class: str
    what: str
    status: str  # "shipped" | "in_progress" | "planned"
    reuse: str  # which existing surface it slots into
    note: str = ""


# --- What runs today -------------------------------------------------

SHIPPED: tuple[ShippedPipeline, ...] = (
    ShippedPipeline(
        name="axe-core",
        pipeline="axe",
        engine="axe dev API, injected into the rendered DOM",
        scs="dozens (1.1.1 presence, 1.3.1, 1.4.3, 2.4.x, 4.1.2, meta-viewport, …)",
        needs_ai=False,
        note="Largest coverage source by rule count. Needs the rendered "
        "DOM — runs on every page now that JS rendering is the default.",
    ),
    ShippedPipeline(
        name="Keyboard-trap probe",
        pipeline="keyboard",
        engine="Deterministic Playwright (Tab-walk, Esc, iframe checks)",
        scs="2.1.2 No Keyboard Trap",
        needs_ai=False,
    ),
    ShippedPipeline(
        name="Responsive / zoom probe",
        pipeline="responsive",
        engine="Deterministic Playwright (viewport mutation + CSS inject)",
        scs="1.4.4 Resize Text, 1.4.10 Reflow, 1.4.12 Text Spacing",
        needs_ai=False,
    ),
    ShippedPipeline(
        name="Focus probe",
        pipeline="focus",
        engine="Deterministic Playwright (focus geometry + tabindex)",
        scs="2.4.11 Focus Not Obscured, 2.4.3 Focus Order (positive tabindex)",
        needs_ai=False,
    ),
    ShippedPipeline(
        name="Image-of-text (VLM)",
        pipeline="image",
        engine="OCR (Tesseract) + VLM via Ollama",
        scs="1.4.5 Images of Text",
        needs_ai=True,
    ),
    ShippedPipeline(
        name="Semantic analyzer",
        pipeline="semantic",
        engine="Per-SC Text-LLM via Ollama",
        scs="2.4.4 Link Purpose (In Context)",
        needs_ai=True,
        note="Machinery is built; only 2.4.4 has a registered analyzer. "
        "The roadmap below is the queue to close this gap.",
    ),
)


# --- The AI roadmap --------------------------------------------------
# Status reconciled against the repo on 2026-06-19. Two items the
# original triage marked "in progress" have NO code and are corrected to
# "planned"; 2.4.6 / 3.3.2 are in the orchestrator's default criteria but
# have no analyzer class, so they're skipped at runtime — also "planned".

ROADMAP: tuple[RoadmapItem, ...] = (
    RoadmapItem(
        wcag="1.4.5",
        issue="Images of Text",
        ai_fit="Strong",
        model_class="VLM",
        what="Decide whether an image is really rendered text.",
        status="shipped",
        reuse="image pipeline",
    ),
    RoadmapItem(
        wcag="2.4.4",
        issue="Link Purpose (In Context)",
        ai_fit="Strong",
        model_class="Text-LLM",
        what="Judge whether link text + context conveys destination.",
        status="shipped",
        reuse="semantic pipeline",
    ),
    RoadmapItem(
        wcag="1.3.2",
        issue="Meaningful Sequence",
        ai_fit="Strong",
        model_class="VLM",
        what="Screenshot + DOM-order text; does source order match the visual reading order?",
        status="planned",
        reuse="VLM + Playwright runtime",
        note="No code yet — original triage marked in-progress.",
    ),
    RoadmapItem(
        wcag="3.2.3",
        issue="Consistent Navigation",
        ai_fit="Strong",
        model_class="Embedding (~30M, CPU)",
        what="Embed each page's nav, cluster; outliers = nav diverges.",
        status="planned",
        reuse="cross-page analyzer (net-new)",
        note="No code yet — original triage marked in-progress.",
    ),
    RoadmapItem(
        wcag="2.4.6",
        issue="Headings and Labels",
        ai_fit="Strong",
        model_class="Text-LLM (~1B)",
        what="Does a heading describe its section? Would a user know what a field wants?",
        status="shipped",
        reuse="Text-LLM static (extractor + registry)",
        note="Heading descriptiveness shipped (HeadingsAndLabelsAnalyzer); "
        "label descriptiveness still pending.",
    ),
    RoadmapItem(
        wcag="3.3.2",
        issue="Labels or Instructions",
        ai_fit="Strong",
        model_class="Text-LLM",
        what="Per field: combine label + placeholder + aria-describedby; "
        "is it enough to know what to enter?",
        status="shipped",
        reuse="Text-LLM static (extractor + registry)",
        note="LabelsOrInstructionsAnalyzer judges label/instruction sufficiency.",
    ),
    RoadmapItem(
        wcag="1.2.1",
        issue="Audio transcript (prerecorded)",
        ai_fit="Strong",
        model_class="Text-LLM (~1B)",
        what="Read DOM around each <audio>; is a transcript present or linked within reach?",
        status="shipped",
        reuse="Text-LLM static (extractor + registry)",
        note="AudioTranscriptAnalyzer checks <audio> for a reachable transcript.",
    ),
    RoadmapItem(
        wcag="1.2.4",
        issue="Captions (prerecorded video)",
        ai_fit="Strong",
        model_class="ASR (Whisper) + Text-LLM",
        what="Transcribe the audio track, diff vs the published <track>; "
        "flag missing / garbage / desynced captions.",
        status="planned",
        reuse="new analyzer module",
    ),
    RoadmapItem(
        wcag="2.2.2",
        issue="Pause, Stop, Hide",
        ai_fit="Strong",
        model_class="VLM (video)",
        what="3-second capture; anything auto-moving >5s with no pause control?",
        status="planned",
        reuse="VLM + Playwright runtime (short capture)",
    ),
    RoadmapItem(
        wcag="2.4.3",
        issue="Focus Order",
        ai_fit="Strong",
        model_class="Deterministic Playwright",
        what="Flag positive tabindex (F44) that forces a broken manual tab order.",
        status="shipped",
        reuse="live-page focus probe (no model needed)",
        note="Positive-tabindex check shipped; full reading-order judgement "
        "still needs a human.",
    ),
    RoadmapItem(
        wcag="2.4.11",
        issue="Focus Not Obscured (Minimum)",
        ai_fit="Strong",
        model_class="Deterministic Playwright",
        what="Focus each element; is its centre covered by a sticky/fixed overlay?",
        status="shipped",
        reuse="live-page focus probe (no model needed)",
        note="FocusProbe — turned out to be doable deterministically "
        "(elementFromPoint geometry), no VLM required.",
    ),
    RoadmapItem(
        wcag="3.2.4",
        issue="Consistent Identification",
        ai_fit="Strong",
        model_class="Embedding + VLM",
        what="Find visually similar components across pages; verify their accessible names match.",
        status="planned",
        reuse="cross-page analyzer (net-new)",
    ),
    RoadmapItem(
        wcag="3.2.6",
        issue="Consistent Help",
        ai_fit="Strong",
        model_class="Embedding + geometry",
        what="Locate help affordances across the crawl; flag pages where "
        "help moves to a non-standard location.",
        status="planned",
        reuse="cross-page analyzer (net-new)",
    ),
)


@dataclass(frozen=True)
class StatusCounts:
    """Roll-up for the page header."""

    shipped: int = 0
    in_progress: int = 0
    planned: int = 0
    labels: dict[str, str] = field(
        default_factory=lambda: {
            "shipped": "Shipped",
            "in_progress": "In progress",
            "planned": "Planned",
        }
    )


def roadmap_counts() -> StatusCounts:
    """Tally roadmap items by status for the summary line."""
    return StatusCounts(
        shipped=sum(1 for r in ROADMAP if r.status == "shipped"),
        in_progress=sum(1 for r in ROADMAP if r.status == "in_progress"),
        planned=sum(1 for r in ROADMAP if r.status == "planned"),
    )
