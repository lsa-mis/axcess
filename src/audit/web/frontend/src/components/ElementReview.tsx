import { useEffect, useId, useState, type FormEvent } from "react";
import { ApiError, api } from "../api/client";
import type { OccurrenceReview, ReviewDecision } from "../api/types";
import { useModalDialog } from "../hooks/useModalDialog";
import { REVIEW_DECISION_HELP, REVIEW_DECISION_LABEL } from "../lib/terms";
import PillGroup from "./newScan/PillGroup";
import { Button, ReviewDecisionChip } from "./ui";

/** What the review holds while it is being edited, before Save. */
export type ReviewDraft = { decision: ReviewDecision | null; notes: string };

type Choice = ReviewDecision | "none";
const CHOICES: Choice[] = ["none", "report", "repeat"];

const MAX_NOTES = 2000;

/**
 * A person's review of the element the page inspector has circled:
 * "Checked by a person" and Issue notes.
 *
 * What it does. In the element facts panel, a region of fixed width shows
 * the review at a glance: the decision as a chip (ReviewDecisionChip, the
 * neutral chip occurrence statuses use, so the three decisions look alike
 * and differ by their words), the issue notes cut to two lines, and a
 * "Review this element" button. The button opens a dialog with the choice, the
 * notes, "Save review" (saves and closes) and "Close without saving" (keeps
 * the unsaved edit for this element while the page is open).
 *
 * Why here, and why a dialog. The developer chose it from three designs.
 * Rejected: the form in a column beside the saved page (it made the saved
 * page 22rem narrower, so some sites switched to a narrower layout of their
 * own) and the form beside the element facts (taller than the facts, it
 * pushed the saved page below the fold on a laptop screen, so after Next the
 * element was out of view, and it cut the facts' reading width short). The
 * line and button are short, so the saved page stays where it was, at full
 * width. The cost is one more action per element (open the dialog); the
 * line keeps each element's review in view without opening it.
 *
 * Accessibility. A native modal <dialog> opened with showModal(), as the
 * app's other dialogs (useModalDialog): the browser keeps focus inside,
 * makes the page behind inert, closes it on Escape, and returns focus to
 * "Review this element" (WAI-ARIA APG Dialog (Modal) pattern,
 * https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/, met by the native
 * element). It is named by its heading and described by which element it is
 * for (aria-labelledby, aria-describedby). Opening it puts focus on the
 * chosen radio, where the arrow keys choose from. Every control has a visible label that
 * is its name (SC 2.5.3 Label in Name, Level A), and every button says what
 * it does in its own words (repo rule 8), so the dialog has no icon-only
 * close button: "Close without saving" and Escape close it.
 *
 * "Checked by a person" is a native radio group of three, as the developer
 * asked: one choice of several (APG Radio Group pattern, met by native
 * inputs). Rejected: a toggle switch (on/off only) and toggle buttons
 * (nothing stops two being pressed). "Not checked yet" is the starting
 * choice because a radio cannot be cleared; it also takes a decision back.
 *
 * The decision chip is the button's description (aria-describedby), so a
 * screen reader hears the current decision on the button (the notes are
 * left out: up to 2,000 characters is too long to hear on every focus),
 * and it is words, never colour alone (SC 1.4.1 Use of Color, Level A). "Saved." is said in a
 * polite status region outside the dialog, always in the page, since the
 * dialog closes on save (SC 4.1.3 Status Messages, Level AA). A failed save
 * keeps the dialog open with the reason as an alert and the edit intact.
 *
 * Suggested notes. An element with no saved notes opens with notes built
 * from the scan (``suggestIssueNotes``: page state, element, problem, in
 * the ITS team's own note style), as the developer chose, and the hint
 * says so first: "Suggested from the scan. Read and edit it before you
 * save." It is a suggestion, not an edit: nothing is stored until Save
 * review, and saved notes are never replaced by one. Rejected: a
 * "Suggest issue notes" button, one more step for every element.
 *
 * Hints say only what the code does: the server removes email addresses,
 * phone numbers and sign-in tokens from notes (``redact_text``).
 */
export default function ElementReview({
  scanId,
  pageId,
  elementKey,
  elementName,
  a11yFindingIds,
  pageImageIds,
  suggestedNotes,
  saved,
  draft,
  onDraftChange,
  onSaved,
}: {
  scanId: number;
  pageId: number;
  /** Which element this is, so a message about another element is not shown. */
  elementKey: string;
  /** What the element is, as the facts say it, for the dialog's description. */
  elementName: string;
  a11yFindingIds: number[];
  pageImageIds: number[];
  /** Issue notes built from the scan (``suggestIssueNotes``); "" when none. */
  suggestedNotes: string;
  /** The review as stored, or null when no one has saved one. */
  saved: OccurrenceReview | null;
  /** This element's unsaved edit, kept by the inspector while the page is open. */
  draft: ReviewDraft | undefined;
  onDraftChange: (next: ReviewDraft | undefined) => void;
  onSaved: (review: OccurrenceReview) => void;
}) {
  const idBase = useId();
  const titleId = `${idBase}-title`;
  const subjectId = `${idBase}-subject`;
  const summaryId = `${idBase}-summary`;
  const notesId = `${idBase}-notes`;
  const notesHintId = `${idBase}-notes-hint`;
  const [open, setOpen] = useState(false);
  const dialogRef = useModalDialog(open);
  const [saving, setSaving] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  // On opening, focus the chosen radio. The browser would focus the first
  // control, "Not checked yet", even when another is chosen, and the arrow
  // keys would then move from the wrong place.
  useEffect(() => {
    if (open) dialogRef.current?.querySelector<HTMLInputElement>("input[type=radio]:checked")?.focus();
  }, [open, dialogRef]);
  // A message belongs to the element it was about.
  useEffect(() => {
    setAnnouncement("");
    setFailure(null);
  }, [elementKey]);

  const stored: ReviewDraft = { decision: saved?.decision ?? null, notes: saved?.notes ?? "" };
  const value = draft ?? stored;
  const dirty = value.decision !== stored.decision || value.notes !== stored.notes;
  // In the dialog, an element with no saved notes starts with the notes
  // suggested from the scan. The suggestion is not an edit: until the reader
  // changes something, nothing is "not saved", and the region above keeps
  // saying "None yet". Saved notes are never replaced by a suggestion.
  const suggesting = !draft && !stored.notes && Boolean(suggestedNotes);
  const editing: ReviewDraft = suggesting ? { ...stored, notes: suggestedNotes } : value;
  const count = a11yFindingIds.length + pageImageIds.length;

  function change(next: ReviewDraft) {
    const same = next.decision === stored.decision && next.notes === stored.notes;
    // Emptying a suggestion is an edit: dropping the draft would bring the
    // suggestion straight back, and the box could never be cleared.
    const clearedSuggestion = suggesting || (draft !== undefined && !stored.notes && !next.notes);
    onDraftChange(same && !clearedSuggestion ? undefined : next);
  }

  function close() {
    setOpen(false);
    setFailure(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setFailure(null);
    try {
      const result = await api.saveOccurrenceReview(scanId, pageId, {
        a11y_finding_ids: a11yFindingIds,
        page_image_ids: pageImageIds,
        decision: editing.decision,
        notes: editing.notes,
      });
      onSaved(result);
      onDraftChange(undefined);
      setOpen(false);
      setAnnouncement(
        result.notes !== editing.notes.trim()
          ? "Saved. Email addresses, phone numbers or sign-in tokens were removed from the notes."
          : "Saved.",
      );
    } catch (error) {
      setFailure(
        error instanceof ApiError
          ? error.message
          : "The Axcess server did not respond. Check that it is still running.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-w-0 text-sm text-fg">
      {/* The review at a glance: the decision as a chip, then the notes. */}
      <p id={summaryId}>
        <span className="block font-semibold">Your review:</span>{" "}
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <ReviewDecisionChip value={value.decision} />
          {dirty && <span className="font-semibold"> Not saved yet</span>}
        </span>
      </p>
      {/* Two lines at most, so the panel stays about as tall as the element
          facts beside it and the saved page below keeps its place; the
          whole note is in the dialog. Clipped for the eye only: a screen
          reader reads all of it. */}
      <p className="mt-1.5 line-clamp-2 whitespace-pre-line [overflow-wrap:anywhere]">
        <span className="font-semibold">Issue notes: </span>
        {value.notes.trim() ? value.notes : <span className="text-fg-muted">None yet</span>}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <Button
          type="button"
          variant="secondary"
          aria-describedby={summaryId}
          onClick={() => {
            setAnnouncement("");
            setOpen(true);
          }}
        >
          Review this element
        </Button>
        <p role="status" className="text-sm text-fg empty:sr-only">
          {announcement}
        </p>
      </div>

      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        aria-describedby={subjectId}
        // Escape and "Close without saving" end the same way: closed, with
        // the unsaved edit kept for this element.
        onClose={close}
        className="max-h-[90vh] w-[min(94vw,36rem)] overflow-y-auto rounded-xs border border-border bg-surface p-0 text-fg shadow-raised backdrop:bg-black/40"
      >
        <form onSubmit={submit}>
          <div className="border-b border-border px-6 py-4">
            <h2 id={titleId} className="text-xl font-semibold">
              Review this element
            </h2>
            <p id={subjectId} className="mt-0.5 text-base text-fg-muted [overflow-wrap:anywhere]">
              {elementName}
              {count > 1 && `. Your review applies to all ${count} occurrences on this element.`}
            </p>
          </div>
          <div className="space-y-4 px-6 py-5">
            <PillGroup<Choice>
              layout="list"
              name={`${idBase}-decision`}
              label="Checked by a person"
              value={editing.decision ?? "none"}
              onChange={(choice) => change({ ...editing, decision: choice === "none" ? null : choice })}
              options={CHOICES.map((choice) => ({
                value: choice,
                label: REVIEW_DECISION_LABEL[choice],
                hint: REVIEW_DECISION_HELP[choice] || undefined,
              }))}
            />
            <div className="flex min-w-0 flex-col gap-1">
              <label htmlFor={notesId} className="text-sm font-semibold text-fg">
                Issue notes
              </label>
              <textarea
                id={notesId}
                value={editing.notes}
                maxLength={MAX_NOTES}
                rows={5}
                aria-describedby={notesHintId}
                onChange={(event) => change({ ...editing, notes: event.target.value })}
                className="min-h-target w-full resize-y rounded-xs border border-border bg-surface px-3 py-2 text-base text-fg focus:border-umich-blue focus:outline-none"
              />
              <p id={notesHintId} className="text-xs text-fg-muted">
                {suggesting && (
                  <span className="mb-0.5 block font-semibold text-fg">
                    Suggested from the scan. Read and edit it before you save.
                  </span>
                )}
                Write it for the vendor: where the problem is, what is wrong, and what to fix. Up
                to 2,000 characters. Email addresses, phone numbers and sign-in tokens are removed
                when you save.
              </p>
            </div>
            {failure && (
              <p role="alert" className="text-sm font-semibold text-sev-critical">
                Axcess could not save your review. {failure} Your changes are still here. Try
                again.
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-border px-6 py-4">
            <Button
              type="submit"
              variant="primary"
              // aria-disabled, not disabled: a disabled button drops the
              // focus the reader just put on it.
              aria-disabled={saving || undefined}
            >
              {saving ? "Saving review…" : "Save review"}
            </Button>
            <Button type="button" variant="secondary" onClick={close}>
              Close without saving
            </Button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
