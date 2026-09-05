import { useState } from "react";
import { Link } from "react-router";
import { Check, ChevronRight, Minus } from "lucide-react";
import { cn } from "../lib/cn";
import { Card } from "./ui";
import type {
  IssueRow,
  ScanMethodCoverage,
  ScanMethodState,
} from "../api/types";

/**
 * What this scan actually checked, a ledger, one row per method.
 *
 * The previous treatment printed every method's label, description, result and
 * caveat as a permanent two-column grid of cards: nine paragraphs of hedging
 * on a page whose job is to say what happened. The caveats matter, so they are
 * kept in full, they just sit behind the row they qualify, where a reader
 * goes when they want to know what a method does and does not prove.
 */
const METHOD_STATE_LABEL: Record<ScanMethodState, string> = {
  not_selected: "Not selected",
  waiting: "Waiting",
  running: "Checking",
  checked: "Ran",
  partial: "Partly ran",
  not_run: "Did not run",
  coverage_unknown: "Not recorded",
};

/**
 * Which detector's findings belong to which method, so a row can answer "and
 * what did it find?" rather than only "did it run?". ``rendered`` and
 * ``interaction`` are not detectors, they are how a page is reached, and
 * whatever they expose is then checked by axe and Alfa, so they are counted
 * differently below.
 */
const METHOD_PIPELINE: Partial<Record<ScanMethodCoverage["key"], IssueRow["pipeline"][]>> = {
  axe: ["axe"],
  alfa: ["alfa"],
  keyboard: ["keyboard"],
  responsive: ["responsive"],
  image: ["image", "protected_image"],
  semantic: ["semantic"],
};

export default function MethodCoverageLedger({
  scanId,
  methods,
  rows,
  className = "",
}: {
  scanId: number;
  methods: ScanMethodCoverage[];
  rows: IssueRow[] | undefined;
  className?: string;
}) {
  const ran = methods.filter((method) => method.state === "checked" || method.state === "partial");

  return (
    <Card className={cn("overflow-hidden", className)}>
      <div className="px-4 pb-3 pt-4">
        <h2 className="text-base font-semibold tracking-[-0.015em] text-fg">
          What this scan actually checked
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          {ran.length} of {methods.length} methods ran. Open a row for what it
          does and does not prove.
        </p>
      </div>
      <ul className="border-t border-border">
        {methods.map((method) => (
          <MethodRow key={method.key} scanId={scanId} method={method} rows={rows} />
        ))}
      </ul>
    </Card>
  );
}

function MethodRow({
  scanId,
  method,
  rows,
}: {
  scanId: number;
  method: ScanMethodCoverage;
  rows: IssueRow[] | undefined;
}) {
  const [open, setOpen] = useState(false);
  const ran = method.state === "checked" || method.state === "partial";
  const found = findingsFor(method, rows);

  return (
    <li className="border-b border-border last:border-b-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        className={cn(
          "flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface-muted/60",
          open && "bg-surface-subtle",
        )}
      >
        {/* The icon is a second, non-color signal for whether a method ran,
            the chip alone would leave the state to a colour difference. */}
        {ran ? (
          <Check className="h-[18px] w-[18px] shrink-0 text-fg" aria-hidden />
        ) : (
          <Minus className="h-[18px] w-[18px] shrink-0 text-border-strong" aria-hidden />
        )}
        <span className={cn("min-w-0 flex-1 text-sm font-semibold", ran ? "text-fg" : "text-fg-subtle")}>
          {method.label}
        </span>
        <span className="hidden shrink-0 text-sm tabular-nums text-fg-muted sm:block">
          {ran ? method.result : "n/a"}
        </span>
        <StateChip state={method.state} />
        <ChevronRight
          className={cn(
            "h-[18px] w-[18px] shrink-0 text-fg-subtle transition-transform duration-150",
            open && "rotate-90",
          )}
          aria-hidden
        />
      </button>
      <div hidden={!open} className="bg-surface-subtle px-4 pb-4 pl-[46px] pt-0">
        <p className="max-w-[78ch] text-sm leading-relaxed text-fg-muted sm:hidden">
          {ran ? method.result : "This method was not part of this scan."}
        </p>
        <p className="mt-1 max-w-[78ch] text-sm leading-relaxed text-fg-muted">
          {method.description}
        </p>
        {found && (
          <p className="mt-2 max-w-[78ch] text-sm font-medium text-fg">
            {found.text}
            {found.count > 0 && (
              <>
                {" "}
                <Link
                  to={`/scans/${scanId}/issues`}
                  className="font-semibold text-umich-blue underline underline-offset-2"
                >
                  See them in Issues
                </Link>
              </>
            )}
          </p>
        )}
        <p className="mt-2 max-w-[78ch] text-xs leading-relaxed text-fg-subtle">
          {method.caveat}
        </p>
      </div>
    </li>
  );
}

/**
 * "and this is what we found" for one method.
 *
 * Detector methods answer with their own issue groups. ``interaction`` is the
 * exception worth spelling out: clicking through DOM states does not detect
 * anything itself, it just reaches markup that would otherwise be invisible to
 * the scan, so what it "found" is the evidence that only exists after a
 * control was used. Saying "none" there is a real result, not a gap, it means
 * nothing in this report is hiding behind a menu.
 */
function findingsFor(
  method: ScanMethodCoverage,
  rows: IssueRow[] | undefined,
): { text: string; count: number } | null {
  if (!rows || (method.state !== "checked" && method.state !== "partial")) return null;

  if (method.key === "interaction") {
    const revealed = rows.filter((row) =>
      row.locations.some((location) => location.revealed_by),
    );
    return revealed.length === 0
      ? {
          text: "Found: no issue in this report depends on a state that only appears after a click.",
          count: 0,
        }
      : {
          text: `Found: ${revealed.length} issue group${revealed.length === 1 ? "" : "s"} with evidence that only appears after a control is used.`,
          count: revealed.length,
        };
  }

  const pipelines = METHOD_PIPELINE[method.key];
  if (!pipelines) return null;
  const count = rows.filter((row) => pipelines.includes(row.pipeline)).length;
  return count === 0
    ? { text: "Found: no issue groups.", count: 0 }
    : {
        text: `Found: ${count} issue group${count === 1 ? "" : "s"}.`,
        count,
      };
}

function StateChip({ state }: { state: ScanMethodState }) {
  const ran = state === "checked" || state === "partial";
  return (
    <span
      className={cn(
        "hidden shrink-0 rounded-full border px-2 py-0.5 text-2xs font-semibold sm:inline-block",
        ran
          ? "border-umich-blue/30 bg-umich-blue/10 text-umich-blue"
          : state === "running"
            ? "border-umich-maize/60 bg-umich-maize/15 text-fg"
            : state === "not_run"
              ? "border-sev-major/30 bg-sev-major-bg text-sev-major"
              : "border-border bg-surface text-fg-muted",
      )}
    >
      {METHOD_STATE_LABEL[state]}
    </span>
  );
}
