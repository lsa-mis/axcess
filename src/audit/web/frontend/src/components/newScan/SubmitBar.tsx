import { Button } from "../ui";

/** The note under Start in the summary rail, which is Start's description. */
export const SUBMIT_NOTE_ID = "scan-submit-note";

/**
 * Cancel and Start, at the top right of the New scan page, where the rest of
 * the app puts a page's action. They sit in the page header, outside the
 * form, so Start names the form it submits (`form`).
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
