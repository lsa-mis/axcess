import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleCheck, CircleHelp, CircleX, Copy, Sparkles } from "lucide-react";
import { ApiError, api } from "../api/client";
import type {
  SuggestionAudience,
  SuggestionAvailability,
  SuggestionOccurrenceKind,
  SuggestionRecord,
} from "../api/types";
import {
  AI_SUGGESTION,
  SUGGESTION_AUDIENCE_LABEL,
  SUGGESTION_CHECK_LABEL,
  SUGGESTION_ERROR_LABEL,
  SUGGESTION_STATUS_LABEL,
} from "../lib/terms";
import Tabs from "./Tabs";
import { Button, Card, relativeTime } from "./ui";

/**
 * "Suggest a fix (AI)" for one occurrence, and the suggestion it produces.
 *
 * **What it does.** One button asks the local AI model (Ollama, on this
 * computer) to suggest a fix. The request waits in a queue and runs in the
 * background; this panel checks on it every few seconds and shows the answer
 * in two views, one for developers (code) and one for content editors (steps
 * and text to paste). It opens on the view for whoever usually fixes this kind
 * of issue.
 *
 * **Why it is a button and not automatic.** Writing a suggestion takes the
 * computer tens of seconds. Writing one for every occurrence on page load
 * would slow a running scan and fill the database with answers nobody asked
 * for. Asking is cheap; one click is the cost.
 *
 * **Why the warning is always shown.** The model can be wrong, and a
 * plausible but wrong fix is worse than none. The note "It can be wrong.
 * Check it before you use it." sits under the heading of every suggestion,
 * not in a tooltip (W3C COGA "Making Content Usable", paraphrased: put
 * important information where people will see it, not behind a control;
 * https://www.w3.org/TR/coga-usable/). Axcess never applies a suggestion; a
 * person copies it.
 *
 * **Focus.** The trigger button is replaced by the queue status once
 * clicked, so its focus would fall to the page body. Focus moves to the
 * "AI suggestion" heading instead, which is the start of the new content
 * (SC 2.4.3 Focus Order, Level A). Status changes are announced through one
 * polite live region (SC 4.1.3 Status Messages, Level AA), never by moving
 * focus a second time while someone is reading.
 *
 * **Views.** Developer / editor use the shared `Tabs` in `filter` mode,
 * toggle buttons with `aria-pressed`, not an ARIA tablist; the `Tabs`
 * rationale explains why the app has one keyboard model for chip rows
 * (SC 3.2.4 Consistent Identification, Level AA).
 *
 * **Code.** Before and after code wrap inside their boxes rather than
 * scroll sideways, so the panel reflows at 320 px (SC 1.4.10 Reflow,
 * Level AA). Code is shown as text; nothing the model wrote is rendered as
 * HTML.
 *
 * **Check result.** Each outcome has its own icon *and* sentence, never
 * colour alone (SC 1.4.1 Use of Color, Level A). A pass is described as one
 * rule passing on the suggested code, because that is all it is: it does not
 * show the page meets WCAG.
 */
export default function FixSuggestion({
  scanId,
  kind,
  occurrenceId,
  availability,
  headingLevel = 4,
}: {
  scanId: number;
  kind: SuggestionOccurrenceKind;
  occurrenceId: number;
  availability: SuggestionAvailability;
  /**
   * The panel's heading level: 4 inside an occurrence card under an h3, 2
   * where it sits straight under the page's h1 (the Page inspector), so the
   * outline never skips a level (SC 1.3.1 Info and Relationships, Level A).
   */
  headingLevel?: 2 | 3 | 4;
}) {
  const Heading = `h${headingLevel}` as "h2" | "h3" | "h4";
  const queryClient = useQueryClient();
  const headingId = useId();
  const panelId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const focusHeading = useRef(false);
  const queryKey = ["suggestion", scanId, kind, occurrenceId];

  const { data: record, error: loadError } = useQuery({
    queryKey,
    queryFn: () => api.getLatestSuggestion(scanId, kind, occurrenceId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });

  const settle = (next: SuggestionRecord) => {
    queryClient.setQueryData(queryKey, next);
  };
  const ask = useMutation({
    mutationFn: () => api.requestSuggestion(scanId, kind, occurrenceId),
    onSuccess: (next) => {
      focusHeading.current = true;
      settle(next);
    },
  });
  const stop = useMutation({
    mutationFn: (id: number) => api.cancelSuggestion(scanId, id),
    onSuccess: settle,
  });

  // Runs after the heading exists, so the move is to real content.
  useEffect(() => {
    if (focusHeading.current && headingRef.current) {
      focusHeading.current = false;
      headingRef.current.focus();
    }
  });

  const actionError = ask.error ?? stop.error;
  const errorText = actionError
    ? actionError instanceof ApiError
      ? actionError.message
      : "Axcess could not reach the server. Try again."
    : null;

  if (loadError) {
    return (
      <p className="mt-3 text-sm text-fg-muted">
        Axcess could not load the AI suggestion for this occurrence. Reload the page to try again.
      </p>
    );
  }

  if (!record || record.status === "cancelled") {
    return (
      <div className="mt-3 flex flex-col items-start gap-1.5">
        <Button type="button" onClick={() => ask.mutate()} disabled={ask.isPending}>
          <Sparkles className="h-4 w-4" aria-hidden />
          Suggest a fix (AI)
        </Button>
        {errorText && (
          <p role="alert" className="text-sm text-sev-critical">
            {errorText}
          </p>
        )}
      </div>
    );
  }

  const waiting = record.status === "queued" || record.status === "running";

  return (
    <section aria-labelledby={headingId} className="mt-4 border-t border-border pt-3">
      <Heading
        id={headingId}
        ref={headingRef}
        tabIndex={-1}
        className="flex items-center gap-1.5 text-sm font-semibold text-fg"
      >
        <Sparkles className="h-4 w-4" aria-hidden />
        {AI_SUGGESTION}
      </Heading>
      <p className="mt-1 text-xs text-fg-muted">
        Written by AI on this computer. It can be wrong. Check it before you use it.
      </p>

      <p role="status" aria-live="polite" aria-atomic="true" className="mt-2 text-sm text-fg">
        {statusSentence(record, availability)}
      </p>

      {waiting && (
        <div className="mt-2">
          <Button type="button" onClick={() => stop.mutate(record.id)} disabled={stop.isPending}>
            Stop
          </Button>
        </div>
      )}

      {record.status === "failed" && (
        <div className="mt-2">
          <Button type="button" onClick={() => ask.mutate()} disabled={ask.isPending}>
            Try again
          </Button>
        </div>
      )}

      {record.status === "ready" && record.result && (
        <ReadySuggestion
          scanId={scanId}
          record={record}
          panelId={panelId}
          onSettle={settle}
          onAskAgain={() => ask.mutate()}
          asking={ask.isPending}
        />
      )}

      {errorText && (
        <p role="alert" className="mt-2 text-sm text-sev-critical">
          {errorText}
        </p>
      )}
    </section>
  );
}

function statusSentence(record: SuggestionRecord, availability: SuggestionAvailability): string {
  const slow = availability.scan_running ? " A scan is running, so this may take longer." : "";
  switch (record.status) {
    case "queued":
      return record.queue_position && record.queue_position > 1
        ? `${SUGGESTION_STATUS_LABEL.queued}. ${record.queue_position - 1} ahead of it.${slow}`
        : `${SUGGESTION_STATUS_LABEL.queued}. It is next.${slow}`;
    case "running":
      return `${SUGGESTION_STATUS_LABEL.running}. This can take a minute.${slow}`;
    case "failed":
      return `${SUGGESTION_STATUS_LABEL.failed}. ${
        record.error_code ? SUGGESTION_ERROR_LABEL[record.error_code] : SUGGESTION_ERROR_LABEL.internal
      }`;
    case "cancelled":
      return SUGGESTION_STATUS_LABEL.cancelled;
    case "ready":
      return `${SUGGESTION_STATUS_LABEL.ready}.`;
  }
}

function ReadySuggestion({
  scanId,
  record,
  panelId,
  onSettle,
  onAskAgain,
  asking,
}: {
  scanId: number;
  record: SuggestionRecord;
  panelId: string;
  onSettle: (next: SuggestionRecord) => void;
  onAskAgain: () => void;
  asking: boolean;
}) {
  const result = record.result!;
  const [audience, setAudience] = useState<SuggestionAudience>(record.audience_default);
  const feedback = useMutation({
    mutationFn: (value: SuggestionRecord["feedback"]) =>
      api.setSuggestionFeedback(scanId, record.id, value),
    onSuccess: onSettle,
  });
  const toggle = (value: "helpful" | "not_helpful") =>
    feedback.mutate(record.feedback === value ? null : value);

  // Default view first: the person who usually fixes this kind of issue
  // should not have to switch before they read (COGA: put the most likely
  // need first).
  const order: SuggestionAudience[] =
    record.audience_default === "editor" ? ["editor", "developer"] : ["developer", "editor"];

  return (
    <div className="mt-2 space-y-3">
      <p className="text-sm leading-relaxed text-fg">{result.summary}</p>

      {(result.needs_manual_check || result.confidence === "guess") && (
        <p className="text-sm text-fg-muted">
          <span className="font-semibold text-fg">Check by hand: </span>
          {result.manual_check_reason ??
            (result.confidence === "guess"
              ? "The check that found this needs a person's judgement, so treat this as a starting point."
              : "A person should confirm the fix works on the real page.")}
        </p>
      )}

      <Tabs
        mode="filter"
        label="Who the suggestion is for"
        items={order.map((key) => ({ key, label: SUGGESTION_AUDIENCE_LABEL[key] }))}
        value={audience}
        onChange={(key) => setAudience(key as SuggestionAudience)}
        controls={panelId}
      />

      <div id={panelId}>
        {audience === "developer" ? (
          <DeveloperPanel record={record} />
        ) : (
          <EditorPanel record={record} />
        )}
      </div>

      <p className="text-xs text-fg-muted">
        Written by {record.text_model}
        {record.vision_model ? ` with ${record.vision_model} reading the picture` : ""}
        {record.finished_at ? `, ${relativeTime(record.finished_at)}` : ""}. Not included in
        exports.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Was this suggestion helpful?" className="flex flex-wrap gap-2">
          <Button
            type="button"
            aria-pressed={record.feedback === "helpful"}
            onClick={() => toggle("helpful")}
            disabled={feedback.isPending}
          >
            {record.feedback === "helpful" && <Check className="h-4 w-4" aria-hidden />}
            Helpful
          </Button>
          <Button
            type="button"
            aria-pressed={record.feedback === "not_helpful"}
            onClick={() => toggle("not_helpful")}
            disabled={feedback.isPending}
          >
            {record.feedback === "not_helpful" && <Check className="h-4 w-4" aria-hidden />}
            Not helpful
          </Button>
        </div>
        <Button type="button" variant="ghost" onClick={onAskAgain} disabled={asking}>
          Suggest again
        </Button>
      </div>
      {feedback.isError && (
        <p role="alert" className="text-sm text-sev-critical">
          Axcess could not save your answer. Try again.
        </p>
      )}
    </div>
  );
}

const CODE_BOX =
  "mt-1 whitespace-pre-wrap break-words rounded-2xs border border-border bg-surface-muted px-2 py-1.5 font-mono text-xs text-fg";

function DeveloperPanel({ record }: { record: SuggestionRecord }) {
  const { developer, before_html } = record.result!;
  return (
    <div className="space-y-3">
      <p className="text-sm leading-relaxed text-fg">{developer.explanation}</p>
      {(before_html || developer.after_html) && (
        <div className="grid gap-3 lg:grid-cols-2">
          {before_html && (
            <div className="min-w-0">
              <p className="text-2xs font-semibold text-fg-subtle">Before: the element code (HTML) the scan found</p>
              <pre className={CODE_BOX}>{before_html}</pre>
            </div>
          )}
          {developer.after_html && (
            <div className="min-w-0">
              <p className="text-2xs font-semibold text-fg-subtle">After: suggested element code (HTML)</p>
              <pre className={CODE_BOX}>{developer.after_html}</pre>
              <CopyButton value={developer.after_html} name="suggested element code" />
            </div>
          )}
        </div>
      )}
      {developer.css && (
        <div className="min-w-0">
          <p className="text-2xs font-semibold text-fg-subtle">Suggested styles (CSS)</p>
          <pre className={CODE_BOX}>{developer.css}</pre>
          <CopyButton value={developer.css} name="suggested styles" />
        </div>
      )}
      <CheckOutcome record={record} />
    </div>
  );
}

function EditorPanel({ record }: { record: SuggestionRecord }) {
  const { editor } = record.result!;
  return (
    <div className="space-y-3">
      {editor.steps.length > 0 && (
        <ol className="list-decimal space-y-1 pl-5 text-sm text-fg">
          {editor.steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      )}
      {editor.paste_text.map((item, index) => (
        <div key={index} className="min-w-0">
          <p className="text-2xs font-semibold text-fg-subtle">{item.label}</p>
          <p className={CODE_BOX}>{item.value}</p>
          <CopyButton value={item.value} name={item.label} />
        </div>
      ))}
      {editor.needs_developer && (
        <p className="text-sm text-fg-muted">
          A content editor cannot fully fix this alone. Ask a developer to use the developer view.
        </p>
      )}
      {editor.steps.length === 0 && editor.paste_text.length === 0 && !editor.needs_developer && (
        <p className="text-sm text-fg-muted">The AI model wrote no steps for content editors.</p>
      )}
    </div>
  );
}

function CheckOutcome({ record }: { record: SuggestionRecord }) {
  const outcome = record.check_outcome ?? "not_checked";
  const Icon = outcome === "passed" ? CircleCheck : outcome === "still_fails" ? CircleX : CircleHelp;
  const tone =
    outcome === "passed" ? "text-ok" : outcome === "still_fails" ? "text-sev-critical" : "text-fg-muted";
  return (
    <p className="flex items-start gap-1.5 text-sm text-fg">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} aria-hidden />
      <span>
        {SUGGESTION_CHECK_LABEL[outcome]}
        {outcome === "passed" &&
          ". This checks one rule on the suggested code only. It does not show that the page meets WCAG."}
        {outcome === "not_checked" &&
          ". Only some rule check (axe) issues can be checked this way."}
      </span>
    </p>
  );
}

/**
 * Copies one piece of the suggestion. The visible word is "Copy"; the
 * hidden rest names what is copied, so the accessible name contains the
 * visible text (SC 2.5.3 Label in Name, Level A). The "Copied" confirmation
 * is a status message (SC 4.1.3), keyed per attempt so a second copy is
 * announced too. Without a clipboard (plain http on a network address) it
 * says to select the text by hand instead of failing silently.
 */
function CopyButton({ value, name }: { value: string; name: string }) {
  const attempts = useRef(0);
  const [result, setResult] = useState<{ attempt: number; ok: boolean } | null>(null);
  const copy = async () => {
    attempts.current += 1;
    const attempt = attempts.current;
    try {
      await navigator.clipboard.writeText(value);
      setResult({ attempt, ok: true });
    } catch {
      setResult({ attempt, ok: false });
    }
  };
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
      <Button type="button" size="sm" className="min-h-target" onClick={copy}>
        <Copy className="h-3.5 w-3.5" aria-hidden />
        Copy<span className="sr-only"> {name}</span>
      </Button>
      <span role="status" className="text-xs text-fg-muted">
        {result && (
          <span key={result.attempt}>
            {result.ok ? "Copied" : "Your browser blocked copying. Select the text and copy it."}
          </span>
        )}
      </span>
    </div>
  );
}

/**
 * Said once for the screen, not beside every occurrence: the setting is on
 * but the model cannot run, so each button would only fail the same way.
 * One note says why and who can fix it.
 */
export function SuggestionsBlockedNote({
  status,
  className = "mb-5",
}: {
  status: SuggestionAvailability;
  className?: string;
}) {
  const why =
    status.reason === "database_update_needed"
      ? "the Axcess database needs an update first (run make migrate)."
      : status.reason === "model_missing"
        ? `the AI model (${status.missing_models.join(", ") || status.text_model}) is not installed in Ollama.`
        : "the local AI service (Ollama) is not running.";
  return (
    <Card className={`${className} p-4 text-sm text-fg-muted`}>
      AI fix suggestions are turned on, but cannot run because {why} Ask the person who set up
      Axcess.
    </Card>
  );
}
