import { useId } from "react";
import { cn } from "../../lib/cn";
import { Button } from "../ui";
import { SUMMARY } from "./copy";

/**
 * Start, Cancel and Reset, at the foot of the summary rail. Start is never
 * disabled: a disabled button cannot say why, so pressing it runs
 * validation and the alert at the top of the form explains. While a request
 * is in flight it is `aria-disabled`, which keeps focus where it is and
 * still announces the state. The note under Start is its description.
 */
export default function SubmitBar({
  label,
  pendingLabel,
  pending,
  note,
  onCancel,
  onReset,
  className,
}: {
  label: string;
  pendingLabel: string;
  pending: boolean;
  note?: string;
  onCancel: () => void;
  onReset: () => void;
  className?: string;
}) {
  const noteId = useId();
  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <Button
        type="submit"
        variant="primary"
        size="lg"
        className="w-full"
        aria-disabled={pending || undefined}
        aria-describedby={note ? noteId : undefined}
        onClick={(event) => {
          if (pending) event.preventDefault();
        }}
      >
        {pending ? pendingLabel : label}
      </Button>
      {note && (
        <p id={noteId} className="text-xs text-fg-muted">
          {note}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button type="button" onClick={onCancel} className="min-w-[7.5rem] flex-1">
          Cancel
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={onReset}
          className="underline decoration-1 underline-offset-2 hover:decoration-2"
        >
          {SUMMARY.reset}
        </Button>
      </div>
    </div>
  );
}
