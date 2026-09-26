import type { ReactNode } from "react";
import { useModalDialog } from "../hooks/useModalDialog";
import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, ExternalLink, Info, X, type LucideIcon } from "lucide-react";
import { api } from "../api/client";
import { Button, Card } from "./ui";
import IssuePagesTable from "./IssuePagesTable";
import type { AbilityLabel, IssueDetail, IssueRow } from "../api/types";
import { HIDDEN_ISSUE_FIELDS } from "../lib/hiddenIssueFields";
import { REVIEW_TYPE_LABEL } from "../lib/terms";

/**
 * Every page one issue affects, with its occurrences and their
 * screenshots: the body of the issue evidence page. What the issue is, the
 * fix and how to verify it live in ``IssueGuidanceDialog``, opened from the
 * page header, so the page itself leads with where the issue is.
 */
export default function IssueEvidence({
  scanId,
  issueKey,
  origin = "Issues",
  backTo,
}: {
  scanId: number;
  issueKey: string;
  /**
   * The view this evidence is being read in, and the path back to it. They
   * travel with every page link below so the topbar trail on the page's own
   * views names the view the reviewer actually came from — the only way back
   * in the desktop app, which has no browser back button. Defaults to the
   * Issues list, where this is expanded inline.
   */
  origin?: string;
  backTo?: string;
}) {
  const parentTo = backTo ?? `/scans/${scanId}/issues`;
  const { data, isLoading, error } = useQuery({
    queryKey: ["issue-detail", scanId, issueKey],
    queryFn: () => api.getIssueDetail(scanId, issueKey),
    enabled: Number.isFinite(scanId) && !!issueKey,
  });

  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        This issue&rsquo;s details could not load. Nothing in the saved report has changed.
        Reload the page to try again.
      </Card>
    );
  }
  if (!data || isLoading) {
    return <p className="px-4 py-6 text-sm text-fg-muted" role="status">Loading issue details…</p>;
  }

  const { row, pages } = data;

  return (
    <div className="space-y-4 p-4">
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">
            Pages with this issue
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {pages.length} page{pages.length !== 1 ? "s" : ""}
            </span>
          </h2>
        </div>
        <IssuePagesTable
          scanId={scanId}
          issueKey={issueKey}
          row={row}
          pages={pages}
          backTo={parentTo}
          origin={origin}
        />
      </Card>
    </div>
  );
}

/**
 * An issue's guidance, in a dialog opened from the top right of its page:
 * what it is, the next step (the fix for a barrier, the checks for a lead),
 * and why it matters with how to verify. Every section is open, so reading it
 * takes one click, not one per section. A native modal ``<dialog>``, like
 * Compare's terms: the browser traps focus, Escape closes it, and focus
 * returns to the button that opened it.
 */
export function IssueGuidanceDialog({
  open,
  onClose,
  detail,
}: {
  open: boolean;
  onClose: () => void;
  detail: IssueDetail;
}) {
  const ref = useModalDialog(open);
  return (
    <dialog
      ref={ref}
      aria-labelledby="issue-guidance-title"
      aria-describedby="issue-guidance-subject"
      onClose={onClose}
      // The dialog itself scrolls, not a box inside it: its close button is
      // focusable, so the scrolling area is reachable by keyboard (axe's
      // scrollable-region-focusable), and the header stays pinned. The
      // scroll padding keeps a focused link from scrolling in under that
      // header (SC 2.4.11).
      className="max-h-[90vh] w-[min(94vw,52rem)] scroll-pt-28 overflow-y-auto rounded-xs border border-border bg-surface p-0 text-fg shadow-raised backdrop:bg-black/40"
    >
      <div className="sticky top-0 z-[1] flex items-start justify-between gap-4 border-b border-border bg-surface px-6 py-4">
        <div className="min-w-0">
          <h2 id="issue-guidance-title" className="text-xl font-semibold">Issue guidance</h2>
          <p id="issue-guidance-subject" className="mt-0.5 text-base text-fg-muted">{detail.row.title}</p>
        </div>
        <Button type="button" variant="ghost" onClick={onClose} aria-label="Close issue guidance">
          <X className="h-5 w-5" aria-hidden />
        </Button>
      </div>
      <div className="px-6 py-6">
        <IssueGuidance detail={detail} />
      </div>
    </dialog>
  );
}

/**
 * One at-a-glance fact: its name, its value large, and an optional short
 * note under the value. A ``dt`` and one or two ``dd``s, so the pairing is
 * announced, not just drawn.
 */
function FactTile({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="rounded-xs border border-border bg-surface-subtle px-4 py-3">
      <dt className="text-sm text-fg-muted">{label}</dt>
      <dd className="mt-1 text-lg font-semibold tabular-nums leading-snug text-fg">{value}</dd>
      {note && <dd className="mt-0.5 text-sm text-fg-muted">{note}</dd>}
    </div>
  );
}

/** One guidance section: a heading under the dialog's own h2, then its content. */
function GuidanceSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-border pt-6 first:border-t-0 first:pt-0">
      <h3 className="mb-3 text-lg font-semibold text-fg">{title}</h3>
      {children}
    </section>
  );
}

/**
 * "Done when" as a note of its own, labelled, so it reads as the finish line
 * and a screen reader announces it by name rather than as one more line.
 */
function DoneWhen({ text }: { text: string }) {
  return (
    <div role="note" aria-label="Done when" className="mt-4 max-w-[70ch] rounded-xs border border-ok/30 bg-ok-bg px-4 py-3">
      <p className="text-base leading-7 text-fg">
        <span className="font-semibold text-ok">Done when: </span>
        {text}
      </p>
    </div>
  );
}

/** The guidance sections themselves, all expanded. */
function IssueGuidance({ detail }: { detail: IssueDetail }) {
  const { row, description, why_matters, fix_steps, verify_manual,
    verify_automated, acceptance, help_url } = detail;
  const lane = LANES[row.review_lane] ?? LANES.informational;
  const isInformational = row.review_lane === "informational";
  const isLead = row.review_lane === "expert_review";
  const LaneIcon = lane.icon;

  // A lead is confirmed before anyone fixes it, so its checks are the next
  // step and the fix goes in the background; a barrier is the other way round.
  const verifySteps = [verify_manual, verify_automated].filter(Boolean) as string[];
  const nextSteps = isInformational ? [] : isLead ? verifySteps : fix_steps;
  const nextTitle = isLead ? "How to confirm it" : "How to fix it";
  const hasBackground =
    !!why_matters ||
    (isLead ? fix_steps.length > 0 : verifySteps.length > 0) ||
    (isLead && !!acceptance);

  return (
    <div className="space-y-8">
        <GuidanceSection title={isInformational ? "What Axcess found" : "What it is"}>
          {/* The verdict leads the section and reads as a sentence, not a
              badge: what this record is, what that means for how it may be
              reported, and why the tool raised it. The icon and the words
              carry the lane, so the tint is never the only signal. */}
          <div className={`rounded-xs border border-l-4 p-4 ${lane.className}`}>
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
              <div className="flex min-w-0 items-start gap-3">
                <LaneIcon className={`mt-0.5 h-5 w-5 shrink-0 ${lane.iconClass}`} aria-hidden />
                <div className="min-w-0">
                  <h4 className="text-base font-semibold text-fg">{lane.label}</h4>
                  <p className="mt-1 text-base leading-7 text-fg">{lane.meaning}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pl-8 text-sm">
                <span className="text-fg-muted">
                  Confidence:{" "}
                  <span className="font-semibold text-fg">{capitalize(row.evidence_confidence)}</span>
                </span>
                {help_url && (
                  <a
                    href={help_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-semibold text-umich-blue underline underline-offset-2"
                  >
                    About this rule
                    <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
                    <span className="sr-only">, opens in a new tab</span>
                  </a>
                )}
              </div>
            </div>
            {row.evidence_summary && (
              <p className="mt-3 pl-8 text-base leading-7 text-fg">
                <span className="font-semibold">Why it was flagged: </span>
                {row.evidence_summary}
              </p>
            )}
          </div>

          {/* At a glance, four even tiles read left to right: the level
              asked of the page, how soon to fix it, how far it spreads, and
              who it shuts out. Each is a term and its value, so a screen
              reader reads "Priority, High" and moves on. */}
          <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <FactTile label="WCAG level" value={wcagLevel(row)} />
            {!isInformational && (
              <FactTile label="Priority" value={priorityTier(row.priority)} />
            )}
            <FactTile
              label="Occurrences"
              value={row.occurrence_count.toLocaleString()}
              note={`across ${row.page_count.toLocaleString()} page${row.page_count === 1 ? "" : "s"}`}
            />
            {!isInformational && row.abilities_affected.length > 0 && (
              <FactTile
                label="Affects"
                value={
                  <span className="flex flex-wrap gap-1.5">
                    {row.abilities_affected.map((a: AbilityLabel) => (
                      <span
                        key={a}
                        className="inline-block rounded-full border border-border bg-surface px-2.5 py-0.5 text-sm font-semibold"
                      >
                        {capitalize(a)}
                      </span>
                    ))}
                  </span>
                }
              />
            )}
            {!isInformational && !HIDDEN_ISSUE_FIELDS.has("Difficulty") && row.difficulty !== "Unknown" && (
              <FactTile label="Difficulty" value={row.difficulty} />
            )}
            {!isInformational && !HIDDEN_ISSUE_FIELDS.has("Responsibility") && (
              <FactTile label="Who fixes it" value={capitalize(row.responsibility)} />
            )}
          </dl>
          {!isInformational && (
            <p className="mt-2 text-sm leading-6 text-fg-muted">
              Priority is based on how serious the issue is and how many pages have it. Fix it sooner when both are high.
            </p>
          )}

          <p className="mt-4 max-w-[70ch] text-base leading-7 text-fg">
            {description ? (
              <RuleText text={description} />
            ) : (
              row.evidence_summary ||
              "Axcess recorded this automatically. See the pages with this issue for the details."
            )}
          </p>
        </GuidanceSection>

        {nextSteps.length > 0 && (
          <GuidanceSection title={nextTitle}>
            <ol className="max-w-[70ch] list-decimal space-y-1.5 pl-6 text-base leading-7 text-fg">
              {isLead
                ? nextSteps.map((step, i) => <li key={i}>{step}</li>)
                : nextSteps.map((step, i) => (
                    <li
                      key={i}
                      // Steps include inline <code> / <em> from the YAML.
                      // We trust YAML authors (it's our own rule book).
                      dangerouslySetInnerHTML={{ __html: step }}
                    />
                  ))}
              {isLead && (
                <li className="font-semibold">
                  Look at the issue on the page itself before you report it as a barrier.
                </li>
              )}
            </ol>
            {!isLead && acceptance && (
              <DoneWhen text={acceptance} />
            )}
          </GuidanceSection>
        )}

        {!isInformational && hasBackground && (
          <GuidanceSection
            title={isLead ? "Why it matters, and how to fix it if it is confirmed" : "Why it matters, and how to test the fix"}
          >
            {why_matters && <p className="max-w-[70ch] text-base leading-7 text-fg">{why_matters}</p>}
            {isLead && fix_steps.length > 0 && (
              <>
                <h4 className="mt-5 text-base font-semibold text-fg">How it should work</h4>
                <ol className="mt-2 max-w-[70ch] list-decimal space-y-3 pl-6 text-base leading-7 text-fg">
                  {fix_steps.map((step, i) => (
                    <li key={i} dangerouslySetInnerHTML={{ __html: step }} />
                  ))}
                </ol>
              </>
            )}
            {isLead && acceptance && (
              <DoneWhen text={acceptance} />
            )}
            {!isLead && verifySteps.length > 0 && (
              <>
                <h4 className="mt-5 text-base font-semibold text-fg">How to test the fix</h4>
                <ul className="mt-2 max-w-[70ch] list-disc space-y-3 pl-6 text-base leading-7 text-fg">
                  {verifySteps.map((step, i) => <li key={i}>{step}</li>)}
                </ul>
              </>
            )}
          </GuidanceSection>
        )}
    </div>
  );

}

/**
 * A type's name as the issue page says it: the Issues table's own word
 * (``REVIEW_TYPE_LABEL``), so the page header, the guidance dialog and the
 * table use one word for one thing.
 */
export function issuePageLaneLabel(lane: IssueRow["review_lane"]): string {
  return (LANES[lane] ?? LANES.informational).label;
}

/**
 * How each type reads at the top of the guidance. The meaning line says
 * what the type lets a reviewer do with the issue, in words, so the tint
 * and icon are never the only cue.
 */
const LANES: Record<
  IssueRow["review_lane"],
  { label: string; meaning: string; icon: LucideIcon; className: string; iconClass: string }
> = {
  likely_barrier: {
    label: REVIEW_TYPE_LABEL.likely_barrier,
    meaning: "A check failed a fixed rule, so this is likely to block someone. Fix it, then test the fix.",
    icon: AlertOctagon,
    className: "border-umich-blue/30 border-l-umich-blue bg-umich-blue/5",
    iconClass: "text-umich-blue",
  },
  expert_review: {
    label: REVIEW_TYPE_LABEL.expert_review,
    meaning:
      "Do not call this a confirmed barrier until an expert checks it and records the decision.",
    icon: AlertTriangle,
    className: "border-sev-major/40 border-l-sev-major bg-sev-major-bg",
    iconClass: "text-sev-major",
  },
  informational: {
    label: REVIEW_TYPE_LABEL.informational,
    meaning:
      "This check found no barrier. Axcess keeps this record so you can see what it looked at. " +
      "It is for information only, and you cannot change it.",
    icon: Info,
    className: "border-border border-l-fg-subtle bg-surface-muted",
    iconClass: "text-fg-muted",
  },
};

/**
 * Rule-book prose with its inline ``<code>`` spans rendered as code. Only that
 * one tag is honoured and everything else stays text: a description can carry
 * a scanner diagnostic quoted from the crawled page, which must never become
 * markup.
 */
function RuleText({ text }: { text: string }) {
  const parts = text.split(/<code>([\s\S]*?)<\/code>/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <code key={i} className="rounded-2xs bg-surface-muted px-1 py-px text-[0.9em]">
            {decodeEntities(part)}
          </code>
        ) : (
          decodeEntities(part)
        ),
      )}
    </>
  );
}

function decodeEntities(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&");
}

/** The WCAG level asked of the page, in words: "Level AA", "Best practice", or "Does not apply". */
function wcagLevel(row: IssueRow): string {
  if (!row.wcag_sc) return "Does not apply";
  return row.conformance === "BP" ? "Best practice" : `Level ${row.conformance}`;
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/** A plain-English band for the priority score (severity × log1p(pages)). */
function priorityTier(priority: number): "High" | "Medium" | "Low" {
  if (priority >= 6) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}

