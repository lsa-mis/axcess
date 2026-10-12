import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, CircleCheck, CircleHelp, CircleX, Copy, Sparkles } from "lucide-react";
import { ApiError, api } from "../api/client";
import type {
  SuggestionAudience,
  SuggestionCheckOutcome,
  SuggestionAvailability,
  SuggestionOccurrenceKind,
  SuggestionRecord,
} from "../api/types";
import { OPENS_NEW_WINDOW,
  AI_SUGGESTION,
  SUGGESTION_AUDIENCE_LABEL,
  SUGGESTION_CHECK_LABEL,
  SUGGESTION_ERROR_LABEL,
  SUGGESTION_OPTION_LABEL,
  SUGGESTION_STATUS_LABEL,
  AI_ISOLATION_REASON_LABEL,
  AI_RUNTIME_START_LABEL,
} from "../lib/terms";
import { useAiSetup } from "../hooks/useAiSetup";
import Tabs from "./Tabs";
import { Button, Card, ExternalLinkButton, LinkButton, relativeTime } from "./ui";

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
 * **Brief by default.** New answers show one precise change sentence, then
 * the saved Before code and two After options. Saved v1 answers keep their
 * original code view. Each new option keeps its own rule-check result visible,
 * including when it could not run; one pass must not imply the other passed.
 * The editor view is unchanged. Model details and manual-check notes remain
 * in "About this suggestion", and the AI warning stays visible (the repo
 * rule to never drop a limitation, privacy or safety fact).
 *
 * **Its own area.** The panel sits in a tinted box with a thick left
 * border, so AI-written content is never mistaken for what the scan found.
 * The heading, icon and border say it as well as the tint, so colour is not
 * the only cue (SC 1.4.1 Use of Color, Level A).
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
  const aiSetup = useAiSetup();
  const [startMessage, setStartMessage] = useState("");
  const startService = useMutation({
    mutationFn: api.startAiRuntime,
    onMutate: () => setStartMessage("Starting the AI service. You can keep browsing other issues."),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["ai-runtime"] });
      if (result.state === "started" || result.state === "already_running") {
        setStartMessage("");
        ask.mutate();
        return;
      }
      const reason = result.reason ? AI_ISOLATION_REASON_LABEL[result.reason] : null;
      setStartMessage(reason ?? AI_RUNTIME_START_LABEL[result.state]);
    },
    onError: () => setStartMessage("The AI service could not start. Try again or check AI settings."),
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
    // With AI off, an unmigrated suggestion table has no saved answer to
    // show. Other read failures remain visible, rather than hiding errors.
    if (!availability.enabled && loadError instanceof ApiError && loadError.status === 404) {
      return null;
    }
    return (
      <p className="mt-3 text-sm text-fg-muted">
        Axcess could not load the AI suggestion for this occurrence. Reload the page to try again.
      </p>
    );
  }

  if (!record || record.status === "cancelled") {
    if (!availability.enabled) return null;
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
    <section
      aria-labelledby={headingId}
      className="mt-4 rounded-xs border border-l-4 border-border border-l-umich-blue bg-umich-blue/5 p-3"
    >
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

      {/* One live region for every status. Visible while waiting or after a
          failure; read to screen readers only once ready, where the answer
          below shows it. */}
      <p
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className={record.status === "ready" ? "sr-only" : "mt-2 text-sm text-fg"}
      >
        {statusSentence(record, availability)}
      </p>

      {waiting && (
        <div className="mt-2">
          <Button type="button" onClick={() => stop.mutate(record.id)} disabled={stop.isPending}>
            Stop
          </Button>
        </div>
      )}

      {/* When the service is simply not running, the fix sits next to the
          error: one "Start AI service" button that starts Axcess's own
          isolated service and then writes this suggestion, so people do not
          have to leave the issue (W3C COGA Making Content Usable,
          https://www.w3.org/TR/coga-usable/, paraphrased: make it easy to
          recover from errors). Rejected: only a link to Settings, which loses
          the person's place. Desktop only: a shared server's AI belongs to
          its administrator, so there the button is not shown. It never
          downloads anything; a missing model points to AI settings, where
          the size is shown before you confirm. aria-disabled plus a click
          guard keep focus on the button while it works (SC 2.4.3 Focus
          Order, Level A), and the polite status region announces progress
          (SC 4.1.3 Status Messages, Level AA). */}
      {record.status === "failed" && availability.enabled && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {record.error_code === "model_unavailable" && aiSetup && (
            <Button
              type="button"
              variant="primary"
              aria-disabled={startService.isPending || ask.isPending || undefined}
              onClick={() => {
                if (!startService.isPending && !ask.isPending) startService.mutate();
              }}
            >
              Start AI service
            </Button>
          )}
          <Button type="button" onClick={() => ask.mutate()} disabled={ask.isPending}>
            Try again
          </Button>
        </div>
      )}
      {record.status === "failed" && aiSetup && (
        <p role="status" aria-live="polite" className={startMessage ? "mt-2 text-sm text-fg" : "sr-only"}>
          {startMessage}
        </p>
      )}
      {record.status === "failed" && startService.data?.state === "model_missing" && (
        <p className="mt-2">
          <LinkButton to="/settings/ai">Choose an AI download</LinkButton>
        </p>
      )}

      {record.status === "ready" && record.result && (
        <ReadySuggestion
          scanId={scanId}
          record={record}
          panelId={panelId}
          onSettle={settle}
          onAskAgain={() => ask.mutate()}
          asking={ask.isPending}
          canAsk={availability.enabled}
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
      return `${SUGGESTION_STATUS_LABEL.running}. You can keep browsing other issues.${slow}`;
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
  canAsk,
}: {
  scanId: number;
  record: SuggestionRecord;
  panelId: string;
  onSettle: (next: SuggestionRecord) => void;
  onAskAgain: () => void;
  asking: boolean;
  canAsk: boolean;
}) {
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

      <AboutSuggestion record={record} />

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
        {canAsk && <Button type="button" variant="ghost" onClick={onAskAgain} disabled={asking}>
          Suggest again
        </Button>}
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
  if ("options" in developer) {
    const [first, second] = developer.options;
    const norm = (v: string | null | undefined) => (v ?? "").replace(/\s+/g, " ").trim();
    const sameCode =
      !!first && !!second &&
      norm(first.after_html) === norm(second.after_html) &&
      norm(first.css) === norm(second.css);
    const shownOptions = sameCode ? [first] : developer.options;
    // Two sequential choices share one saved Before, rather than a third
    // switcher: readers compare the smallest change with the nearby pattern
    // without hiding either check. The Before is scan evidence, never AI text.
    // Rejected: showing only After, which hides what changed. W3C COGA
    // "Making Content Usable", objective 3 (paraphrase: help people understand
    // content), https://www.w3.org/TR/coga-usable/; WCAG 2.2 SC 1.3.1 Info and
    // Relationships (Level A), SC 1.4.10 Reflow (Level AA).
    return (
      <div className="min-w-0 space-y-3">
        <p className="text-sm leading-relaxed text-fg">{developer.change_sentence}</p>
        <div className="min-w-0">
          <p className="text-2xs font-semibold text-fg-subtle">Before</p>
          {before_html ? <pre className={CODE_BOX}>{before_html}</pre> : (
            <p className="mt-1 text-xs text-fg-muted">
              The scan kept no element code for this occurrence.
            </p>
          )}
        </div>
        {/* When the model returns the same code twice, show it once and
            say so, rather than two identical options that look like a
            real choice (W3C COGA "Making Content Usable", paraphrase: no
            duplicate content, https://www.w3.org/TR/coga-usable/). */}
        {sameCode && (
          <p className="text-sm text-fg-muted">The AI gave the same code for both options, so it is shown once.</p>
        )}
        <ol className="list-none space-y-4">
          {shownOptions.map((option) => (
            <li key={option.kind} className="min-w-0 space-y-2">
              <p className="text-sm font-semibold text-fg">{SUGGESTION_OPTION_LABEL[option.kind]}</p>
              <div className="min-w-0">
                <p className="text-2xs font-semibold text-fg-subtle">After</p>
                <pre className={CODE_BOX}>{option.after_html}</pre>
                <CopyButton value={option.after_html} name={`${SUGGESTION_OPTION_LABEL[option.kind]} code`} />
              </div>
              {option.css && <div className="min-w-0">
                <p className="text-2xs font-semibold text-fg-subtle">Suggested styles (CSS)</p>
                <pre className={CODE_BOX}>{option.css}</pre>
                <CopyButton value={option.css} name={`${SUGGESTION_OPTION_LABEL[option.kind]} styles`} />
              </div>}
              <CheckOutcome record={record} outcome={option.check_outcome} showUnchecked />
            </li>
          ))}
        </ol>
        <GuidanceLink record={record} />
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {/* The explanation only when there is no code: then it is the fix. */}
      {!developer.after_html && !developer.css && (
        <p className="text-sm leading-relaxed text-fg">{developer.explanation}</p>
      )}
      {(before_html || developer.after_html) && (
        <div className="grid gap-3 lg:grid-cols-2">
          {/* "Before" sits beside "After" so a developer can see what
              changes. It always comes from the scan (the saved copy), never
              from the model. When the scan kept no element code (a check of
              the whole page, say) the column says so rather than vanishing,
              so the missing comparison is a stated fact, not a silent gap.
              Rejected: hiding the column, which left "After" with nothing
              to compare against and read like a layout bug. Rests on W3C
              COGA "Making Content Usable", objective 3 (paraphrase: help
              people understand what things are and how to use them) and
              the repo rule to never drop a limitation fact. */}
          <div className="min-w-0">
            <p className="text-2xs font-semibold text-fg-subtle">Before</p>
            {before_html ? (
              <pre className={CODE_BOX}>{before_html}</pre>
            ) : (
              <p className="mt-1 text-xs text-fg-muted">
                The scan kept no element code for this occurrence.
              </p>
            )}
          </div>
          {developer.after_html && (
            <div className="min-w-0">
              <p className="text-2xs font-semibold text-fg-subtle">After</p>
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
      <GuidanceLink record={record} />
    </div>
  );
}

function EditorPanel({ record }: { record: SuggestionRecord }) {
  const { editor } = record.result!;
  // Words already in a step are not repeated in a box of their own.
  const pasteText = editor.paste_text.filter(
    (item) => !editor.steps.some((step) => step.includes(item.value.trim())),
  );
  return (
    <div className="space-y-3">
      {editor.steps.length > 0 && (
        <ol className="list-decimal space-y-1 pl-5 text-sm text-fg">
          {editor.steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      )}
      {pasteText.map((item, index) => (
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
      {editor.steps.length === 0 && pasteText.length === 0 && !editor.needs_developer && (
        <p className="text-sm text-fg-muted">The AI model wrote no steps for content editors.</p>
      )}
    </div>
  );
}

function CheckOutcome({ record, outcome = record.check_outcome ?? "not_checked", showUnchecked = false }: {
  record: SuggestionRecord;
  outcome?: SuggestionCheckOutcome;
  showUnchecked?: boolean;
}) {
  // New answers keep even "not checked" beside each option: hiding it would
  // let a neighbouring pass suggest both passed (SC 1.3.1, Level A).
  // Saved single-option answers retain their compact disclosure.
  if (outcome === "not_checked" && !showUnchecked) return null;
  const Icon = outcome === "passed" ? CircleCheck : outcome === "still_fails" ? CircleX : CircleHelp;
  const tone =
    outcome === "passed" ? "text-ok" : outcome === "still_fails" ? "text-sev-critical" : "text-fg-muted";
  return (
    <p className="flex items-start gap-1.5 text-sm text-fg">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} aria-hidden />
      <span>
        {SUGGESTION_CHECK_LABEL[outcome]}
        {outcome === "not_checked" && ". Check this option on the real page."}
        {outcome === "passed" &&
          ". This checks one rule on the suggested code only. It does not show that the page meets WCAG."}
      </span>
    </p>
  );
}

function GuidanceLink({ record }: { record: SuggestionRecord }) {
  // The scan's saved rule URL is the only link source, not AI-written text:
  // fabricated links send readers to the wrong fix. Rejected model-generated
  // links. The shared external link keeps the new-tab warning explicit
  // (WCAG 2.2 SC 3.2.5 Change on Request, Level AAA) and the same link pattern
  // (SC 3.2.4 Consistent Identification, Level AA).
  const url = record.result?.help_url;
  if (!url || !/^https?:\/\//i.test(url)) return null;
  return <ExternalLinkButton href={url} size="sm" className="max-w-full whitespace-normal text-left">
    Read guidance for this rule ({OPENS_NEW_WINDOW})
  </ExternalLinkButton>;
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
  // Says what to do, not only what is wrong: in the desktop app the
  // person reading this is the person who set Axcess up, so "ask the person
  // who set up Axcess" sent them nowhere. Axcess never downloads a model
  // without being asked, so the note offers the setup page (desktop) or the
  // command, and says it is a large download.
  // Rests on WCAG 2.2 SC 3.3.3 Error Suggestion (Level AA; paraphrase: when
  // a fix is known, tell the person) and W3C COGA "Making Content Usable",
  // objective 5 (help users avoid mistakes or know how to correct them),
  // https://www.w3.org/TR/coga-usable/.
  // In the desktop app the first fix offered is Settings > AI features,
  // which downloads Ollama and the models with a button; the terminal
  // command stays for people who run their own Ollama.
  const aiSetup = useAiSetup();
  const setupLink = aiSetup ? (
    <p className="mt-3">
      <LinkButton to="/settings/ai" variant="primary">
        Change AI features
      </LinkButton>
    </p>
  ) : null;
  // Turning AI off never hides saved answers; only request actions disappear.
  // The note links to the one settings page (WCAG 2.2 SC 3.2.4 Consistent
  // Identification, Level AA), not a second local toggle.
  if (status.reason === "turned_off") {
    return <Card className={`${className} p-4 text-sm text-fg-muted`}>
      <p>{aiSetup
        ? "AI features are off. Saved suggestions are still available. Turn AI on in Settings → AI features to ask for a new suggestion."
        : "AI suggestions are off. Saved suggestions are still available. An administrator can turn new suggestions on."}</p>
      {setupLink}
    </Card>;
  }
  if (status.reason === "model_missing") {
    return (
      <Card className={`${className} p-4 text-sm text-fg-muted`}>
        <p>AI fix suggestions are turned on, but the AI model they use is not installed.</p>
        <p className="mt-2">
          To install it, run this in a terminal, then reload this page. It downloads several
          gigabytes.
        </p>
        <pre className={CODE_BOX}>ollama pull {status.text_model}</pre>
        {setupLink}
      </Card>
    );
  }
  if (status.reason === "database_update_needed") {
    return (
      <Card className={`${className} p-4 text-sm text-fg-muted`}>
        AI fix suggestions are turned on, but cannot run because the Axcess database needs an
        update first (run make migrate).
      </Card>
    );
  }
  return (
    <Card className={`${className} p-4 text-sm text-fg-muted`}>
      AI fix suggestions are turned on, but they need Ollama, a free program that runs AI models on
      this computer, and it is not running. Install it from ollama.com (or start it if it is
      installed), then reload this page.
      {setupLink}
    </Card>
  );
}

/**
 * Facts a reader may want but does not need to act: closed by default.
 *
 * A native `<details>` rather than the shared `Disclosure`: `Disclosure`
 * always renders a heading (level 2 or 3), and small print under a heading
 * that is itself level 2 to 4 would add a heading to the outline for every
 * suggestion. `<details>` gives the same open/close behaviour, keyboard
 * support and expanded state without ARIA (W3C "Using ARIA", rule 1,
 * paraphrased: use the native element when it does the job;
 * https://www.w3.org/TR/using-aria/#rule1). The summary is 44 px tall
 * (SC 2.5.5 Target Size (Enhanced), Level AAA, which this repo meets).
 */
function AboutSuggestion({ record }: { record: SuggestionRecord }) {
  const result = record.result!;
  const checkByHand =
    result.needs_manual_check || result.confidence === "guess"
      ? (result.manual_check_reason ??
        (result.confidence === "guess"
          ? "The check that found this needs a person's judgement, so treat this as a starting point."
          : "A person should confirm the fix works on the real page."))
      : null;
  return (
    <details className="group text-xs text-fg-muted">
      {/* The same rotating caret as the shared Disclosure, so it reads as
          the same control (SC 3.2.4 Consistent Identification, Level AA).
          The flex layout hides the browser's own marker. */}
      <summary className="flex min-h-target cursor-pointer list-none items-center gap-2 font-semibold text-fg [&::-webkit-details-marker]:hidden">
        <ChevronRight
          className="h-4 w-4 shrink-0 text-fg-subtle transition-transform duration-200 group-open:rotate-90 motion-reduce:transition-none"
          aria-hidden
        />
        About this suggestion
      </summary>
      <ul className="list-disc space-y-1 pl-5">
        {checkByHand && (
          <li>
            <span className="font-semibold text-fg">Check by hand: </span>
            {checkByHand}
          </li>
        )}
        {result.version !== 2 && (record.check_outcome ?? "not_checked") === "not_checked" && (
          <li>
            {SUGGESTION_CHECK_LABEL.not_checked}. Only some rule check (axe) issues can be checked
            this way.
          </li>
        )}
        <li>
          Written by {record.text_model}
          {record.vision_model ? ` with ${record.vision_model} reading the picture` : ""}
          {record.finished_at ? `, ${relativeTime(record.finished_at)}` : ""}.
        </li>
        <li>Not included in exports.</li>
      </ul>
    </details>
  );
}
