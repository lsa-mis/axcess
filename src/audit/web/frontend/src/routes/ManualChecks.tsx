import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronRight, ClipboardCheck, Search } from "lucide-react";
import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useParams, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { EvaluationRecord, ManualCheck, ManualOutcome } from "../api/types";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Button, Card, EmptyState, PageHeader } from "../components/ui";

const OUTCOME_LABELS: Record<ManualOutcome, string> = {
  not_started: "Not started",
  pass: "Pass",
  fail: "Fail",
  not_tested: "Not tested",
  needs_follow_up: "Needs follow-up",
};

const PRINCIPLES: Record<string, string> = {
  "1": "Perceivable",
  "2": "Operable",
  "3": "Understandable",
  "4": "Robust",
};

type ManualDraft = Pick<ManualCheck, "outcome" | "rationale">;

export default function ManualChecksRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [principleFilter, setPrincipleFilter] = useState("");
  const [methodFilter, setMethodFilter] = useState("");
  const [drafts, setDrafts] = useState<Record<string, ManualDraft>>({});
  const [activeCriterion, setActiveCriterion] = useState("");
  const [selectionAnnouncement, setSelectionAnnouncement] = useState("");
  const [editorFocusRequest, setEditorFocusRequest] = useState(0);
  const criterionRefs = useRef(new Map<string, HTMLElement>());
  const requestedEditorFocus = useRef<string | null>(null);
  const { data: scan } = useQuery({ queryKey: ["scan", id], queryFn: () => api.getScan(id), enabled: Number.isFinite(id) });
  const { data, isLoading, error } = useQuery({ queryKey: ["manual-checks", id], queryFn: () => api.getManualChecks(id), enabled: Number.isFinite(id) });
  const saveEvaluation = useMutation({
    mutationFn: (payload: Partial<EvaluationRecord>) => api.updateEvaluation(id, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["manual-checks", id] }),
  });

  const checks = useMemo(() => data?.checks ?? [], [data?.checks]);
  const counts = useMemo(() => {
    const result = Object.fromEntries(Object.keys(OUTCOME_LABELS).map((key) => [key, 0])) as Record<ManualOutcome, number>;
    checks.forEach((check) => { result[check.outcome] += 1; });
    return result;
  }, [checks]);
  const missingRationale = checks.filter(
    (check) => check.outcome !== "not_started" && !check.rationale.trim(),
  ).length;
  const decided = checks.filter(
    (check) =>
      (check.outcome === "pass" || check.outcome === "fail" || check.outcome === "not_tested") &&
      !!check.rationale.trim(),
  ).length;
  const completion = checks.length ? Math.round((decided / checks.length) * 100) : 0;
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return checks.filter((check) =>
      (!outcomeFilter || check.outcome === outcomeFilter) &&
      (!principleFilter || check.criterion.sc.startsWith(`${principleFilter}.`)) &&
      (!methodFilter || check.criterion.method === methodFilter) &&
      (!needle || `${check.criterion.sc} ${check.criterion.name} ${check.criterion.manual_check}`.toLowerCase().includes(needle)),
    );
  }, [checks, methodFilter, outcomeFilter, principleFilter, query]);
  const requestedCriterion = params.get("criterion") ?? "";
  const selected = filtered.find((check) => check.criterion.sc === requestedCriterion) ?? filtered[0] ?? null;
  const unsavedCount = Object.keys(drafts).length;
  const evaluationCanComplete =
    counts.not_started === 0 && counts.needs_follow_up === 0 && missingRationale === 0;

  useEffect(() => {
    if (!selected) return;
    if (!filtered.some((check) => check.criterion.sc === activeCriterion)) {
      setActiveCriterion(selected.criterion.sc);
    }
  }, [activeCriterion, filtered, selected]);

  useEffect(() => {
    if (
      editorFocusRequest === 0 ||
      !selected ||
      requestedEditorFocus.current !== selected.criterion.sc
    ) return;
    const frame = window.requestAnimationFrame(() => {
      const heading = document.querySelector<HTMLElement>("[data-criterion-heading]");
      requestedEditorFocus.current = null;
      heading?.focus({ preventScroll: true });
      heading?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [editorFocusRequest, selected]);

  useEffect(() => {
    if (!unsavedCount) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const confirmLinkNavigation = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!target || target.getAttribute("href")?.startsWith("#")) return;
      if (!window.confirm(`Leave this page and discard ${unsavedCount} unsaved manual-check draft${unsavedCount === 1 ? "" : "s"}?`)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    document.addEventListener("click", confirmLinkNavigation, true);
    return () => {
      window.removeEventListener("beforeunload", warnBeforeUnload);
      document.removeEventListener("click", confirmLinkNavigation, true);
    };
  }, [unsavedCount]);

  if (error) return <Card className="p-4 text-sm text-sev-critical" role="alert">Couldn&rsquo;t load manual checks. No review decisions were changed.</Card>;
  if (!scan || !data || isLoading) return <div className="text-fg-muted">Loading manual review matrix…</div>;

  const saveContext = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    saveEvaluation.mutate({
      target_standard: String(form.get("target_standard") ?? "WCAG 2.2"),
      target_level: String(form.get("target_level") ?? "AA") as EvaluationRecord["target_level"],
      purpose: String(form.get("purpose") ?? ""),
      scope_included: String(form.get("scope_included") ?? ""),
      scope_excluded: String(form.get("scope_excluded") ?? ""),
      sample_description: String(form.get("sample_description") ?? ""),
      reviewer: String(form.get("reviewer") ?? ""),
      methods_note: String(form.get("methods_note") ?? ""),
      limitations: String(form.get("limitations") ?? ""),
      status: String(form.get("status") ?? "draft") as EvaluationRecord["status"],
    });
  };

  const selectCriterion = (criterion: string, focusEditor = true) => {
    const next = new URLSearchParams(params);
    next.set("criterion", criterion);
    setParams(next, { replace: true });
    setActiveCriterion(criterion);
    const check = checks.find((item) => item.criterion.sc === criterion);
    setSelectionAnnouncement(
      check ? `Selected ${criterion}, ${check.criterion.name}.` : `Selected ${criterion}.`,
    );
    if (focusEditor) {
      requestedEditorFocus.current = criterion;
      setEditorFocusRequest((request) => request + 1);
    }
  };

  const moveCriterionFocus = (event: ReactKeyboardEvent<HTMLElement>, index: number) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown" || event.key === "ArrowRight") nextIndex = Math.min(index + 1, filtered.length - 1);
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") nextIndex = Math.max(index - 1, 0);
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = filtered.length - 1;
    if (nextIndex !== null) {
      event.preventDefault();
      const criterion = filtered[nextIndex]?.criterion.sc;
      if (!criterion) return;
      setActiveCriterion(criterion);
      criterionRefs.current.get(criterion)?.focus();
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectCriterion(filtered[index].criterion.sc);
    }
  };

  const updateDraft = (check: ManualCheck, nextDraft: ManualDraft) => {
    setDrafts((current) => {
      const next = { ...current };
      if (nextDraft.outcome === check.outcome && nextDraft.rationale === check.rationale) {
        delete next[check.criterion.sc];
      } else {
        next[check.criterion.sc] = nextDraft;
      }
      return next;
    });
  };

  const clearDraft = (criterion: string) => {
    setDrafts((current) => {
      const next = { ...current };
      delete next[criterion];
      return next;
    });
  };

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Reports", to: "/scans" }, { label: `Report #${id}`, to: `/scans/${id}` }, { label: "Manual checks" }]}
        title="Manual checks"
        subtitle="Document the experienced human review that automation cannot replace."
      />
      <ReportWorkspaceNav scanId={id} previousScanId={scan.previous_scan_id} />

      <Card className="mb-5 overflow-hidden">
        <div className="grid gap-4 bg-umich-blue p-4 text-white sm:grid-cols-[1fr_auto] sm:items-center">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-white">Expert review progress</p>
            <p className="mt-1 text-2xl font-semibold">{decided} of {checks.length} criteria finalized</p>
            <p className="mt-1 text-sm text-white">“Not tested” is an honest decision when its rationale documents the limitation. A machine result is never substituted for one.</p>
          </div>
          <div className="text-left sm:text-right">
            <strong className="text-3xl tabular-nums">{completion}%</strong>
            <p className="text-xs text-white">{counts.fail} fail · {counts.needs_follow_up} follow-up</p>
          </div>
        </div>
        <div className="h-2 bg-surface-muted" aria-hidden><div className="h-full bg-umich-maize" style={{ width: `${completion}%` }} /></div>
        <p className="sr-only" aria-live="polite">Manual review is {completion}% finalized.</p>
      </Card>

      {unsavedCount > 0 && (
        <Card className="mb-5 border-sev-major/40 bg-sev-major-bg p-3 text-sm" role="status">
          <strong>{unsavedCount} unsaved manual-check draft{unsavedCount === 1 ? "" : "s"}.</strong>{" "}
          Drafts are retained while you move between criteria. Save each decision before leaving this page.
        </Card>
      )}

      <details className="mb-5 rounded-xs border border-border bg-surface shadow-card">
        <summary className="flex min-h-target cursor-pointer items-center justify-between gap-3 p-4 font-semibold text-fg">
          <span>Evaluation context and scope</span>
          <span className="text-xs font-normal text-fg-muted">{data.evaluation.status.replace(/_/g, " ")}</span>
        </summary>
        <form onSubmit={saveContext} className="grid gap-3 border-t border-border p-4 md:grid-cols-2">
          <p className="md:col-span-2 rounded-xs bg-umich-blue/5 p-3 text-sm text-fg-muted">
            Target: WCAG 2.2 AA. U-M&rsquo;s published WCAG 2.1 AA baseline is institutional context; this report does not claim a scan alone establishes conformance.
          </p>
          <Field label="Reviewer"><input name="reviewer" defaultValue={data.evaluation.reviewer} className="field" /></Field>
          <Field label="Evaluation status">
            <select name="status" defaultValue={data.evaluation.status} className="field">
              <option value="draft">Draft</option>
              <option value="in_progress">In progress</option>
              <option value="completed" disabled={!evaluationCanComplete}>
                Completed{!evaluationCanComplete ? ` (${counts.not_started} not started, ${counts.needs_follow_up} follow-up, ${missingRationale} missing rationale)` : ""}
              </option>
            </select>
          </Field>
          <Field label="Target standard"><input name="target_standard" defaultValue={data.evaluation.target_standard} className="field" /></Field>
          <Field label="Target level"><select name="target_level" defaultValue={data.evaluation.target_level} className="field"><option>A</option><option>AA</option><option>AAA</option></select></Field>
          <Field label="Purpose" wide><textarea name="purpose" defaultValue={data.evaluation.purpose} className="field min-h-20" /></Field>
          <Field label="Included scope" wide><textarea name="scope_included" defaultValue={data.evaluation.scope_included} className="field min-h-20" /></Field>
          <Field label="Excluded scope" wide><textarea name="scope_excluded" defaultValue={data.evaluation.scope_excluded} className="field min-h-20" /></Field>
          <Field label="Sample / pages reviewed" wide><textarea name="sample_description" defaultValue={data.evaluation.sample_description} className="field min-h-20" /></Field>
          <Field label="Methods used" wide><textarea name="methods_note" defaultValue={data.evaluation.methods_note} className="field min-h-20" /></Field>
          <Field label="Limitations" wide><textarea name="limitations" defaultValue={data.evaluation.limitations} className="field min-h-20" /></Field>
          <div className="md:col-span-2 flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={saveEvaluation.isPending}>{saveEvaluation.isPending ? "Saving…" : "Save evaluation context"}</Button>
            <span className="text-sm text-fg-muted" role="status">{saveEvaluation.isSuccess ? "Saved." : saveEvaluation.isError ? "Could not save." : ""}</span>
          </div>
        </form>
      </details>

      <section aria-labelledby="matrix-heading">
        <div className="mb-3">
          <h2 id="matrix-heading" className="text-base font-semibold">WCAG 2.2 A/AA review matrix</h2>
          <p className="text-sm text-fg-muted">Filter the matrix, then document one criterion at a time.</p>
        </div>
        <Card className="mb-4 p-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label>
              <span className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle"><Search className="h-3.5 w-3.5" aria-hidden /> Search</span>
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Criterion or test procedure" className="field" />
            </label>
            <FilterSelect label="Outcome" value={outcomeFilter} onChange={setOutcomeFilter} options={[{ value: "", label: `All outcomes (${checks.length})` }, ...Object.entries(OUTCOME_LABELS).map(([value, label]) => ({ value, label: `${label} (${counts[value as ManualOutcome]})` }))]} />
            <FilterSelect label="Principle" value={principleFilter} onChange={setPrincipleFilter} options={[{ value: "", label: "All principles" }, ...Object.entries(PRINCIPLES).map(([value, label]) => ({ value, label }))]} />
            <FilterSelect label="Method" value={methodFilter} onChange={setMethodFilter} options={[{ value: "", label: "All methods" }, { value: "automated", label: "Automated" }, { value: "partial", label: "Partial" }, { value: "ai-assisted", label: "AI-assisted" }, { value: "manual", label: "Manual" }]} />
          </div>
        </Card>

        {filtered.length === 0 ? (
          <EmptyState title="No criteria match" message="Clear a filter to continue the review." />
        ) : (
          <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(17rem,0.75fr)_minmax(26rem,1.4fr)]">
            <label className="lg:hidden">
              <span className="mb-1 block text-sm font-semibold">Selected criterion</span>
              <select value={selected?.criterion.sc ?? ""} onChange={(event) => selectCriterion(event.target.value)} className="field">
                {filtered.map((check) => <option key={check.criterion.sc} value={check.criterion.sc}>{check.criterion.sc} · {check.criterion.name}, {OUTCOME_LABELS[check.outcome]}</option>)}
              </select>
            </label>
            <nav aria-label="Manual check criteria" className="hidden min-w-0 max-h-[68vh] overflow-y-auto pr-1 lg:block">
              <p className="mb-2 text-sm text-fg-muted">{filtered.length} criteria in this view</p>
              <ol className="space-y-2" role="listbox" aria-label="WCAG criteria. Use arrow keys to move and Enter to open.">
                {filtered.map((check, index) => (
                  <li
                    key={check.criterion.sc}
                    ref={(node) => {
                      if (node) criterionRefs.current.set(check.criterion.sc, node);
                      else criterionRefs.current.delete(check.criterion.sc);
                    }}
                    role="option"
                    aria-selected={selected?.criterion.sc === check.criterion.sc}
                    tabIndex={activeCriterion === check.criterion.sc ? 0 : -1}
                    onFocus={() => setActiveCriterion(check.criterion.sc)}
                    onKeyDown={(event) => moveCriterionFocus(event, index)}
                    onClick={() => selectCriterion(check.criterion.sc)}
                    className={`flex min-h-target cursor-pointer items-center gap-3 rounded-xs border p-3 text-left outline-none focus-visible:ring-4 focus-visible:ring-umich-maize ${selected?.criterion.sc === check.criterion.sc ? "border-umich-blue bg-umich-blue/5" : "border-border bg-surface hover:bg-surface-muted"}`}
                  >
                    <OutcomeMark outcome={check.outcome} />
                    <span className="min-w-0 flex-1">
                      <strong className="block text-sm">{check.criterion.sc} · {check.criterion.name}</strong>
                      <span className="mt-0.5 block text-xs text-fg-muted">{OUTCOME_LABELS[check.outcome]} · {check.criterion.method}</span>
                    </span>
                    <ChevronRight className="h-4 w-4 shrink-0 text-umich-blue" aria-hidden />
                  </li>
                ))}
              </ol>
            </nav>
            {selected && (
              <ManualCheckEditor
                key={selected.criterion.sc}
                scanId={id}
                check={selected}
                draft={drafts[selected.criterion.sc] ?? { outcome: selected.outcome, rationale: selected.rationale }}
                onDraftChange={(nextDraft) => updateDraft(selected, nextDraft)}
                onSaved={() => clearDraft(selected.criterion.sc)}
              />
            )}
          </div>
        )}
        <p className="sr-only" aria-live="polite">{selectionAnnouncement}</p>
      </section>
    </>
  );
}

function Field({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return <label className={wide ? "md:col-span-2" : ""}><span className="mb-1 block text-sm font-semibold text-fg">{label}</span>{children}</label>;
}

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<{ value: string; label: string }> }) {
  return <label><span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-fg-subtle">{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className="field">{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function OutcomeMark({ outcome }: { outcome: ManualOutcome }) {
  if (outcome === "pass") return <span className="rounded-full bg-umich-blue p-1 text-white"><Check className="h-3.5 w-3.5" aria-hidden /></span>;
  return <span aria-hidden className={`h-5 w-5 shrink-0 rounded-full border-2 ${outcome === "not_started" ? "border-border-strong" : "border-umich-blue bg-umich-blue/10"}`} />;
}

function ManualCheckEditor({
  scanId,
  check,
  draft,
  onDraftChange,
  onSaved,
}: {
  scanId: number;
  check: ManualCheck;
  draft: ManualDraft;
  onDraftChange: (draft: ManualDraft) => void;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [note, setNote] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  useEffect(() => { setSavedMessage(""); }, [check.criterion.sc]);
  const dirty = draft.outcome !== check.outcome || draft.rationale !== check.rationale;
  const rationaleRequired = draft.outcome !== "not_started" && !draft.rationale.trim();
  const hasSavedDecision =
    check.result_id !== null && check.tested_at !== null && check.outcome !== "not_started";
  const cleanLabel = !hasSavedDecision
    ? "No decision recorded"
    : check.rationale.trim()
      ? "Decision saved"
      : "Rationale required";
  const save = useMutation({
    mutationFn: () => api.updateManualCheck(scanId, check.criterion.sc, draft),
    onSuccess: async () => {
      setSavedMessage("Decision saved.");
      await qc.invalidateQueries({ queryKey: ["manual-checks", scanId] });
      onSaved();
    },
    onError: () => setSavedMessage("Decision could not be saved."),
  });
  const addEvidence = useMutation({
    mutationFn: () => api.addManualEvidence(scanId, check.criterion.sc, { note, evidence_url: evidenceUrl || undefined }),
    onSuccess: () => { setNote(""); setEvidenceUrl(""); setSavedMessage("Evidence note added."); void qc.invalidateQueries({ queryKey: ["manual-checks", scanId] }); },
    onError: () => setSavedMessage("Evidence note could not be added."),
  });

  return (
    <article aria-labelledby="criterion-heading" className="min-w-0 self-start lg:sticky lg:top-4">
      <Card className="overflow-hidden">
        <header className="border-b border-border bg-surface-muted p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{PRINCIPLES[check.criterion.sc[0]]} · Level {check.criterion.level}</p>
              <h3 id="criterion-heading" data-criterion-heading tabIndex={-1} className="mt-1 text-lg font-semibold outline-none focus-visible:ring-4 focus-visible:ring-umich-maize">{check.criterion.sc} · {check.criterion.name}</h3>
            </div>
            <span className="rounded-full border border-border bg-surface px-2 py-1 text-xs font-semibold">{check.criterion.method}</span>
          </div>
        </header>
        <div className="space-y-4 p-4">
          <section>
            <h4 className="flex items-center gap-2 text-sm font-semibold"><ClipboardCheck className="h-4 w-4 text-umich-blue" aria-hidden /> Test procedure</h4>
            <p className="mt-1 text-sm leading-relaxed text-fg-muted">{check.criterion.manual_check}</p>
          </section>
          {check.criterion.automated_check && (
            <section className="rounded-xs border border-border bg-surface-subtle p-3">
              <h4 className="text-sm font-semibold">Automation context</h4>
              <p className="mt-1 text-sm text-fg-muted">{check.criterion.automated_check}</p>
              <p className="mt-1 text-xs text-fg-subtle">Confidence: {check.criterion.confidence}. This does not replace the decision below.</p>
            </section>
          )}
          <div className="grid gap-3 sm:grid-cols-[12rem_1fr]">
            <label><span className="mb-1 block text-sm font-semibold">Outcome</span><select value={draft.outcome} onChange={(event) => onDraftChange({ ...draft, outcome: event.target.value as ManualOutcome })} className="field">{Object.entries(OUTCOME_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label><span className="mb-1 block text-sm font-semibold">Rationale</span><textarea value={draft.rationale} onChange={(event) => onDraftChange({ ...draft, rationale: event.target.value })} aria-describedby={rationaleRequired ? "rationale-required" : undefined} placeholder="What you tested, what happened, and why this outcome is justified" className="field min-h-24" /></label>
          </div>
          {rationaleRequired && (
            <p id="rationale-required" className="text-sm font-semibold text-sev-critical" role="alert">
              Add a rationale before saving this outcome. Record what you tested, what happened, and why the result is justified.
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button type="button" variant="primary" onClick={() => save.mutate()} disabled={!dirty || rationaleRequired || save.isPending}>{save.isPending ? "Saving…" : dirty ? "Save decision" : cleanLabel}</Button>
            {dirty && <span className="text-sm text-fg-muted">Unsaved changes</span>}
            <span className="text-sm text-fg-muted" aria-live="polite">{savedMessage}</span>
          </div>

          <section className="border-t border-border pt-4">
            <h4 className="text-sm font-semibold">Evidence notes ({check.evidence.length})</h4>
            {check.evidence.length > 0 && <ul className="mt-2 space-y-2">{check.evidence.map((item) => <li key={item.id} className="rounded-xs bg-surface-muted p-3 text-sm"><p>{item.note}</p>{item.evidence_url && <a className="mt-1 inline-block break-all" href={item.evidence_url} target="_blank" rel="noreferrer">Open evidence reference</a>}</li>)}</ul>}
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <label className="sm:col-span-2"><span className="sr-only">Evidence note for {check.criterion.sc}</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add an evidence note: page, method, observation, and expected result" className="field min-h-20" /></label>
              <label><span className="sr-only">Evidence URL for {check.criterion.sc}</span><input type="url" value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} placeholder="Optional evidence URL" className="field" /></label>
              <Button type="button" onClick={() => addEvidence.mutate()} disabled={!note.trim() || addEvidence.isPending}>{addEvidence.isPending ? "Adding…" : "Add evidence note"}</Button>
            </div>
          </section>
        </div>
      </Card>
    </article>
  );
}
