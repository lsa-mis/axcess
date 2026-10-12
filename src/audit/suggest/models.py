"""Typed boundaries for AI fix suggestions (browser API and model output)."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class EditorViewV2(EditorView):
    steps: list[Annotated[str, Field(min_length=1, max_length=MAX_SHORT_TEXT)]] = Field(
        default_factory=list, max_length=MAX_STEPS
    )


class ModelAnswer(BaseModel):
    """Exactly the JSON the model must return. Extra keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)
    developer: DeveloperView
    editor: EditorView
    needs_manual_check: bool = True
    manual_check_reason: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)


class CodeOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["minimal", "matches_pattern"]
    label: str = Field(min_length=1, max_length=60)
    after_html: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)
    css: str | None = Field(default=None, max_length=MAX_SNIPPET_CHARS)

    @field_validator("label", "after_html")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give a nonblank label and replacement code.")
        return value


class DeveloperViewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_sentence: str = Field(min_length=1, max_length=240)
    options: list[CodeOption] = Field(min_length=2, max_length=2)

    @field_validator("change_sentence")
    @classmethod
    def short_sentence(cls, value: str) -> str:
        value = value.strip()
        if (
            not value
            or len(value.split()) > 25
            or "\n" in value
            or len(re.split(r"[.!?]\s+", value.strip())) > 1
        ):
            raise ValueError("Use one short sentence, at most 25 words.")
        return value

    @field_validator("options")
    @classmethod
    def ordered_options(cls, value: list[CodeOption]) -> list[CodeOption]:
        if [option.kind for option in value] != ["minimal", "matches_pattern"]:
            raise ValueError("Give the minimal option first, then the pattern option.")
        return value


class ModelAnswerV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    summary: str = Field(min_length=1, max_length=MAX_SHORT_TEXT)
    developer: DeveloperViewV2
    editor: EditorViewV2
    needs_manual_check: bool = True
    manual_check_reason: str | None = Field(default=None, max_length=MAX_SHORT_TEXT)


class CheckedCodeOption(CodeOption):
    """The server adds this result; the model is not allowed to supply it."""

    check_outcome: CheckOutcome


class CheckedDeveloperViewV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_sentence: str = Field(min_length=1, max_length=240)
    options: list[CheckedCodeOption] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def valid_options(self) -> CheckedDeveloperViewV2:
        DeveloperViewV2.model_validate(
            {
                "change_sentence": self.change_sentence,
                "options": [
                    option.model_dump(exclude={"check_outcome"}) for option in self.options
                ],
            }
        )
        return self


class SuggestionResult(BaseModel):
    """What Axcess stores: the model's answer plus facts Axcess adds itself.

    ``before_html`` comes from the stored evidence, never from the model, so
    the "before" side of the comparison is always what the scan saw.
    ``confidence`` is set by Axcess from the kind of check, not by the model.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[1, 2] = 1
    summary: str
    developer: DeveloperView | CheckedDeveloperViewV2
    editor: EditorView
    before_html: str | None
    confidence: Confidence
    needs_manual_check: bool
    manual_check_reason: str | None
    check_rule_id: str | None = None
    help_url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def matching_version(self) -> SuggestionResult:
        if (self.version == 2) != isinstance(self.developer, CheckedDeveloperViewV2):
            raise ValueError("The developer view must match the answer version.")
        return self


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
