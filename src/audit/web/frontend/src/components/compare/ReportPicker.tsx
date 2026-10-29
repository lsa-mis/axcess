import { useEffect, useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { Button, Card, Select } from "../ui";
import { parseServerTime } from "../../lib/serverTime";
import { dateText } from "./format";

/** A report that can be chosen: a completed public scan of this site. */
export type PickerReport = { id: number; started_at: string };

/**
 * The reports to choose from, oldest first, in the order the server picks a
 * baseline (start time, then id; `comparison.site_history`).
 *
 * `history` is the site's most recent completed reports (at most 20,
 * `HISTORY_LIMIT`). `known` is the pair on screen, which can be older than
 * that window when a saved link names it; it is added so the form can
 * always show what is being compared. Anything outside the window is older
 * than everything in it.
 */
export function pickerReports(history: PickerReport[], known: PickerReport[]): PickerReport[] {
  const inHistory = new Set(history.map((report) => report.id));
  const extras = new Map<number, PickerReport>();
  for (const report of known) if (!inHistory.has(report.id)) extras.set(report.id, report);
  const older = [...extras.values()].sort(
    (a, b) => parseServerTime(a.started_at) - parseServerTime(b.started_at) || a.id - b.id,
  );
  return [...older, ...history];
}

/**
 * The pair the form starts with: the one on screen. With no earlier report
 * (this is the site's first), it suggests this report as Before and the
 * next one as After, which is what "Nothing earlier to compare with" asks
 * the reader to do.
 */
function presetPair(ids: number[], afterId: number, beforeId: number | null): [number, number] {
  const at = ids.indexOf(afterId);
  if (at >= 0 && beforeId !== null && ids.includes(beforeId)) return [beforeId, afterId];
  if (at > 0) return [ids[at - 1], afterId];
  if (at === 0) return [afterId, ids[1]];
  return [ids[ids.length - 2], ids[ids.length - 1]];
}

/**
 * "Reports to compare": two choices and a button that open the comparison
 * of any two completed reports of this site. It shows which two reports the
 * page compares, and it is the one way to change them.
 *
 * Why it is built this way (keep these when you change it):
 *
 * - One form, at the top of the page, preset to the pair on screen. It
 *   replaced the sentence "Comparing this report with report #N" and the
 *   link "Compare with the previous report instead": the form says the same
 *   and is also how to change it, so it is one control for one job. The
 *   trend's "Compare with this report" links were removed for the same
 *   reason (see TrendChart). W3C COGA, "Making Content Usable"
 *   (https://www.w3.org/TR/coga-usable/, paraphrased): use one consistent
 *   way to do one thing, and help users avoid mistakes. Research:
 *   2026-10-28 (GitHub compare and Lighthouse CI use two named pickers on
 *   the compare page for the same job).
 * - Rejected: checkboxes or radio columns on the Reports list (no rule for
 *   exactly two, cannot say which is Before, lost on sort and refresh), and
 *   a "Select a run to compare" dialog (a modal on top of a choice this
 *   page can hold, and not shareable by URL).
 * - The labels say which report is older: "Before (older report)" and
 *   "After (newer report)". A comparison always reads from the earlier
 *   report to the later one, as the server requires. Visible labels in a
 *   fieldset with a legend: SC 1.3.1 Info and Relationships and SC 3.3.2
 *   Labels or Instructions, both Level A.
 * - Choosing a report moves nothing; the page changes only when the button
 *   is pressed. SC 3.2.2 On Input, Level A: "Changing the setting of any
 *   user interface component does not automatically cause a change of
 *   context unless the user has been advised of the behavior before using
 *   the component."
 * - The shared `Select`, not a native <select>. The research assumed a
 *   native control; this app's Select is an APG select-only combobox
 *   (ui.tsx says why), and every dropdown in the app is that one, so this
 *   one behaves like the rest (SC 3.2.4 Consistent Identification, Level
 *   AA). Its options are few and ordered newest first, the order of the
 *   Reports list.
 * - A wrong pair is caught here, before the page changes, and said in
 *   words under Before: what is wrong and how to fix it. The message is
 *   tied to Before with `aria-describedby`, Before is marked
 *   `aria-invalid`, and focus moves to it, so a screen reader reads the
 *   message with the control that needs the fix (SC 3.3.1 Error
 *   Identification, Level A; SC 3.3.3 Error Suggestion, Level AA; the
 *   GOV.UK error message pattern,
 *   https://design-system.service.gov.uk/components/error-message/). Not
 *   also a `role="alert"`: focus already brings the message, and an alert
 *   would read it twice. Changing either choice clears it, since the
 *   message may no longer be true.
 * - The choices are the site's 20 most recent completed reports (the
 *   trend's `HISTORY_LIMIT`). When the site has more, a line under the
 *   choices says so, and is the fieldset's description, rather than an
 *   older report silently missing. Sign-in scans and scans that did not
 *   finish are never offered: the server cannot compare them.
 * - The row wraps into one column on a narrow screen (SC 1.4.10 Reflow,
 *   Level AA), in reading order: Before, After, then the button (SC 2.4.3
 *   Focus Order, Level A). Every control is 44 pixels tall (`min-h-target`,
 *   SC 2.5.5 Target Size (Enhanced), Level AAA).
 * - The new comparison drops the table's filters, search and sort: they
 *   were chosen for other rows.
 */
export default function ReportPicker({
  reports,
  afterId,
  beforeId,
  shown,
  total,
}: {
  /** Oldest first (`pickerReports`). At least two. */
  reports: PickerReport[];
  /** The report whose page this is: After unless it is the site's first. */
  afterId: number;
  /** The report it is compared with, or null when there is none. */
  beforeId: number | null;
  /** Reports in the site's history list, and every completed report of the site. */
  shown: number;
  total: number;
}) {
  const navigate = useNavigate();
  const formId = useId();
  const beforeSelectId = `${formId}-before`;
  const afterSelectId = `${formId}-after`;
  const errorId = `${formId}-error`;
  const limitId = `${formId}-limit`;
  const ids = reports.map((report) => report.id);
  const [presetBefore, presetAfter] = presetPair(ids, afterId, beforeId);
  const [before, setBefore] = useState(String(presetBefore));
  const [after, setAfter] = useState(String(presetAfter));
  const [error, setError] = useState<string | null>(null);
  // Bumped on every refused submit, so a second refusal moves focus again.
  const [refused, setRefused] = useState(0);

  // Back to the pair on screen whenever the page shows another one.
  useEffect(() => {
    setBefore(String(presetBefore));
    setAfter(String(presetAfter));
    setError(null);
  }, [presetBefore, presetAfter]);

  // After the render that wires the message to Before, so it is read with it.
  useEffect(() => {
    if (refused > 0) document.getElementById(beforeSelectId)?.focus();
  }, [refused, beforeSelectId]);

  // Newest first, as the Reports list orders a site's scans.
  const options = [...reports].reverse().map((report) => ({
    value: String(report.id),
    label: `Report #${report.id}, scanned ${dateText(report.started_at)}`,
  }));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const b = ids.indexOf(Number(before));
    const a = ids.indexOf(Number(after));
    const problem =
      before === after
        ? "You chose the same report for Before and After. Choose an older report for Before."
        : b > a
          ? "The report for Before is newer than the one for After. Choose an older report for Before."
          : null;
    if (problem) {
      setError(problem);
      setRefused((n) => n + 1);
      return;
    }
    navigate(`/scans/${after}/compare?compare_to=${before}`);
  };

  const limited = shown < total;
  return (
    <Card className="mb-5 p-4">
      <form onSubmit={submit} noValidate>
        <fieldset className="m-0 min-w-0 border-0 p-0" aria-describedby={limited ? limitId : undefined}>
          {/* A heading inside the legend: the group's name, and a stop in the
              headings list like the page's other sections (HTML allows
              heading content in a legend). */}
          <legend className="p-0">
            <h2 className="text-base font-semibold">Reports to compare</h2>
          </legend>
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start">
            <div className="min-w-0">
              <Select
                id={beforeSelectId}
                stacked
                label="Before (older report)"
                value={before}
                onChange={(value) => {
                  setBefore(value);
                  setError(null);
                }}
                options={options}
                aria-invalid={error !== null}
                aria-describedby={error ? errorId : undefined}
              />
              {error && (
                <p id={errorId} className="mt-1 max-w-sm text-sm font-semibold text-sev-critical">
                  {error}
                </p>
              )}
            </div>
            <Select
              id={afterSelectId}
              stacked
              label="After (newer report)"
              value={after}
              onChange={(value) => {
                setAfter(value);
                setError(null);
              }}
              options={options}
            />
            {/* Level with the boxes, not their labels: the labels' line is 20px. */}
            <Button type="submit" variant="primary" className="self-start sm:mt-5">
              Compare these reports
            </Button>
          </div>
          {limited && (
            <p id={limitId} className="mt-3 text-xs text-fg-muted">
              You can choose from the {shown} most recent completed reports of this site. It has {total} in all.
            </p>
          )}
        </fieldset>
      </form>
    </Card>
  );
}
