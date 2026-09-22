import { ArrowRight } from "lucide-react";
import { Button } from "../ui";

/**
 * Start and Cancel. Start is never disabled: a disabled button cannot say
 * why, so pressing it runs validation and the alert at the top of the form
 * explains. While a request is in flight it is `aria-disabled`, which keeps
 * focus where it is and still announces the state.
 */
export default function SubmitBar({
  label,
  pendingLabel,
  pending,
  note,
  onCancel,
  className,
}: {
  label: string;
  pendingLabel: string;
  pending: boolean;
  note?: string;
  onCancel: () => void;
  className?: string;
}) {
  return (
    <div className={className}>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          aria-disabled={pending || undefined}
          onClick={(event) => {
            if (pending) event.preventDefault();
          }}
        >
          {pending ? pendingLabel : label}
          {!pending && <ArrowRight className="h-4 w-4" aria-hidden />}
        </Button>
        <Button type="button" onClick={onCancel}>
          Cancel
        </Button>
        {note && <p className="text-xs text-fg-muted sm:ml-2">{note}</p>}
      </div>
    </div>
  );
}
