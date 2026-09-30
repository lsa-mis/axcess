import { Button } from "../ui";

/** The note under Start in the summary rail, which is Start's description. */
export const SUBMIT_NOTE_ID = "scan-submit-note";

/**
 * Cancel and Start, pinned at the foot of the summary rail beside the form
 * (`ScanForm`'s `actions`), and after the form on a narrow screen, where the
 * rail follows it.
 *
 * Why there. They were at the top right of the page, beside the title,
 * where the rest of the app puts a page's action. But the rest of the app's
 * actions (Export report) act on a page as it is; this one submits a form,
 * and once the reader scrolled down through the settings it was gone. At the
 * top, keyboard order also reached Start before any field. At the foot of
 * the rail:
 * - It is always in view on a wide screen: the rail is sticky, only the
 *   summary inside it scrolls, and its footer is pinned
 *   (`ScanSummaryCard`).
 * - Keyboard and reading order are the form, then the summary of what it
 *   will do, then Start (WCAG 2.2 SC 2.4.3 Focus Order, Level A), so a
 *   reader confirms before starting.
 * - It covers nothing a keyboard reaches: the pinned footer sits over the
 *   summary text only, which holds no controls (SC 2.4.11 Focus Not
 *   Obscured (Minimum), Level AA). A bar fixed to the bottom of the window
 *   was rejected for that reason: it would sit over form fields as they
 *   take focus.
 * - There is one Start, not one at the top and one here: two controls for
 *   one action make a reader wonder how they differ (W3C COGA, "Making
 *   Content Usable", https://www.w3.org/TR/coga-usable/).
 *
 * Start keeps `form`, naming the form it submits, though it now sits inside
 * it: Enter in a field still submits, as the form's default button.
 *
 * Start is never disabled: a disabled button cannot say why, so pressing it
 * runs validation and the alert at the top of the form explains. While a
 * request is in flight it is `aria-disabled`, which keeps focus where it is
 * and still announces the state. The note in the rail (what happens after
 * Start) is its description.
 */
export default function SubmitBar({
  form,
  label,
  pendingLabel,
  pending,
  hasNote,
  onCancel,
}: {
  form: string;
  label: string;
  pendingLabel: string;
  pending: boolean;
  hasNote: boolean;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="button" onClick={onCancel}>
        Cancel
      </Button>
      <Button
        type="submit"
        form={form}
        variant="primary"
        aria-disabled={pending || undefined}
        aria-describedby={hasNote ? SUBMIT_NOTE_ID : undefined}
        onClick={(event) => {
          if (pending) event.preventDefault();
        }}
      >
        {pending ? pendingLabel : label}
      </Button>
    </div>
  );
}
