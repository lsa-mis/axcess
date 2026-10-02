"""Typed boundaries for AI fix suggestions (browser API and model output)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

OccurrenceKind = Literal["a11y", "image"]
SuggestionStatus = Literal["queued", "running", "ready", "failed", "cancelled"]
Audience = Literal["developer", "editor"]
CheckOutcome = Literal["passed", "still_fails", "not_checked"]
Confidence = Literal["likely", "guess"]
Feedback = Literal["helpful", "not_helpful"]
AvailabilityReason = Literal[
    "ready", "turned_off", "database_update_needed", "model_unavailable", "model_missing"
]
ErrorCode = Literal[
    "model_unavailable",
    "model_missing",
    "timeout",
    "bad_answer",
    "restarted",
    "occurrence_gone",
    "internal",
]

# Hard caps on what the model may hand back. The answer is shown to people
# and stored, so an unbounded field is both a layout and a storage risk.
MAX_SNIPPET_CHARS = 4000
MAX_SHORT_TEXT = 400
MAX_PARAGRAPH = 800
MAX_STEPS = 6
MAX_PASTE_ITEMS = 4


class PasteText(BaseModel):
    """Text an editor can paste into a CMS field, with the field's name."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=MAX_PARAGRAPH)


class DeveloperView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=1, max_length=MAX_PARAGRAPH)
    after_html: str | None = Field(default=None, max_length=MAX_SNIPPET_CHARS)
    css: str | None = Field(default=None, max_length=MAX_SNIPPET_CHARS)


class EditorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[str] = Field(default_factory=list, max_length=MAX_STEPS)
    paste_text: list[PasteText] = Field(default_factory=list, max_length=MAX_PASTE_ITEMS)
    needs_developer: bool = False


class ModelAnswer(BaseModel):
    """Exactly the JSON the model must return. Extra keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)
    developer: DeveloperView
    editor: EditorView
    needs_manual_check: bool = True
    manual_check_reason: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)


class SuggestionResult(BaseModel):
    """What Axcess stores: the model's answer plus facts Axcess adds itself.

    ``before_html`` comes from the stored evidence, never from the model, so
    the "before" side of the comparison is always what the scan saw.
    ``confidence`` is set by Axcess from the kind of check, not by the model.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str
    developer: DeveloperView
    editor: EditorView
    before_html: str | None
    confidence: Confidence
    needs_manual_check: bool
    manual_check_reason: str | None
    check_rule_id: str | None = None


class SuggestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrence_kind: OccurrenceKind
    occurrence_id: int = Field(ge=1)


class FeedbackUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: Feedback | None


class SuggestionRecord(BaseModel):
    """One suggestion as the browser sees it."""

    id: int
    scan_id: int
    page_id: int
    occurrence_kind: OccurrenceKind
    occurrence_id: int
    status: SuggestionStatus
    audience_default: Audience
    text_model: str
    vision_model: str | None
    result: SuggestionResult | None
    check_outcome: CheckOutcome | None
    error_code: ErrorCode | None
    error_detail: str | None
    feedback: Feedback | None
    created_at: str
    finished_at: str | None
    # Rows ahead of this one in the queue, so the waiting message can say
    # how long the line is. None once it has started.
    queue_position: int | None = None


class SuggestionAvailability(BaseModel):
    """Whether the feature can be used, and why not."""

    enabled: bool
    # One machine code for the interface to turn into words.
    reason: AvailabilityReason
    text_model: str
    vision_model: str
    missing_models: list[str] = Field(default_factory=list)
    queue_length: int = 0
    scan_running: bool = False
