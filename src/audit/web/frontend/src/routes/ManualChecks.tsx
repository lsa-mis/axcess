import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Button, Card, PageHeader } from "../components/ui";
import type { EvaluationRecord, ManualCheck, ManualOutcome } from "../api/types";

const OUTCOME_LABELS: Record<ManualOutcome, string> = {
  not_started: "Not started",
  pass: "Pass",
  fail: "Fail",
  not_tested: "Not tested",
  needs_follow_up: "Needs follow-up",
};

export default function ManualChecksRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const qc = useQueryClient();
  const { data: scan } = useQuery({ queryKey: ["scan", id], queryFn: () => api.getScan(id), enabled: Number.isFinite(id) });
  const { data, isLoading, error } = useQuery({ queryKey: ["manual-checks", id], queryFn: () => api.getManualChecks(id), enabled: Number.isFinite(id) });
  const saveEvaluation = useMutation({
    mutationFn: (payload: Partial<EvaluationRecord>) => api.updateEvaluation(id, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["manual-checks", id] }),
  });

  if (error) return <Card className="p-4 text-sm text-sev-critical" role="alert">Couldn’t load manual checks.</Card>;
  if (!scan || !data || isLoading) return <div className="text-fg-muted">Loading…</div>;

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

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Reports", to: "/scans" }, { label: `Report #${id}`, to: `/scans/${id}` }, { label: "Manual checks" }]}
        title="Manual checks"
        subtitle="Record the human evaluation that machine evidence cannot replace."
      />
      <ReportWorkspaceNav scanId={id} previousScanId={scan.previous_scan_id} />
      <Card className="mb-5 border-umich-blue/20 bg-umich-blue/5 p-4 text-sm text-fg-muted">
        The report target is WCAG 2.2 AA. U-M’s published WCAG 2.1 AA baseline is institutional context; this report does not claim a scan alone establishes conformance.
      </Card>
      <Card className="mb-6 p-4">
        <h2 className="mb-3 text-base font-semibold">Evaluation context</h2>
        <form onSubmit={saveContext} className="grid gap-3 md:grid-cols-2">
          <Field label="Reviewer"><input name="reviewer" defaultValue={data.evaluation.reviewer} className="field" /></Field>
          <Field label="Evaluation status"><select name="status" defaultValue={data.evaluation.status} className="field"><option value="draft">Draft</option><option value="in_progress">In progress</option><option value="completed">Completed</option></select></Field>
          <Field label="Target standard"><input name="target_standard" defaultValue={data.evaluation.target_standard} className="field" /></Field>
          <Field label="Target level"><select name="target_level" defaultValue={data.evaluation.target_level} className="field"><option>A</option><option>AA</option><option>AAA</option></select></Field>
          <Field label="Purpose" wide><textarea name="purpose" defaultValue={data.evaluation.purpose} className="field min-h-20" /></Field>
          <Field label="Included scope" wide><textarea name="scope_included" defaultValue={data.evaluation.scope_included} className="field min-h-20" /></Field>
          <Field label="Excluded scope" wide><textarea name="scope_excluded" defaultValue={data.evaluation.scope_excluded} className="field min-h-20" /></Field>
          <Field label="Sample / pages reviewed" wide><textarea name="sample_description" defaultValue={data.evaluation.sample_description} className="field min-h-20" /></Field>
          <Field label="Methods used" wide><textarea name="methods_note" defaultValue={data.evaluation.methods_note} className="field min-h-20" /></Field>
          <Field label="Limitations" wide><textarea name="limitations" defaultValue={data.evaluation.limitations} className="field min-h-20" /></Field>
          <div className="md:col-span-2"><Button type="submit" variant="primary" disabled={saveEvaluation.isPending}>{saveEvaluation.isPending ? "Saving…" : "Save evaluation context"}</Button></div>
        </form>
      </Card>
      <section aria-labelledby="checks-heading">
        <h2 id="checks-heading" className="mb-2 text-base font-semibold">WCAG 2.2 A/AA review matrix</h2>
        <p className="mb-3 text-sm text-fg-muted">Use a result and rationale for each criterion you manually evaluate. “Not tested” is an honest outcome, not a pass.</p>
        <div className="space-y-3">{data.checks.map((check) => <ManualCheckCard key={check.criterion.sc} scanId={id} check={check} />)}</div>
      </section>
    </>
  );
}

function Field({ label, wide, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return <label className={wide ? "md:col-span-2" : ""}><span className="mb-1 block text-sm font-semibold text-fg">{label}</span>{children}</label>;
}

function ManualCheckCard({ scanId, check }: { scanId: number; check: ManualCheck }) {
  const qc = useQueryClient();
  const [outcome, setOutcome] = useState<ManualOutcome>(check.outcome);
  const [rationale, setRationale] = useState(check.rationale);
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () => api.updateManualCheck(scanId, check.criterion.sc, { outcome, rationale }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["manual-checks", scanId] }),
  });
  const addEvidence = useMutation({
    mutationFn: () => api.addManualEvidence(scanId, check.criterion.sc, { note }),
    onSuccess: () => { setNote(""); void qc.invalidateQueries({ queryKey: ["manual-checks", scanId] }); },
  });
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-semibold text-fg">{check.criterion.sc} · {check.criterion.name}</h3><p className="mt-1 text-sm text-fg-muted">{check.criterion.manual_check}</p></div><span className="rounded-xs bg-surface-muted px-2 py-1 text-xs font-semibold">{check.criterion.level} · {check.criterion.method}</span></div>
      <div className="mt-3 grid gap-3 md:grid-cols-[12rem_1fr_auto]">
        <label><span className="sr-only">Outcome for {check.criterion.sc}</span><select value={outcome} onChange={(event) => setOutcome(event.target.value as ManualOutcome)} className="field">{Object.entries(OUTCOME_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label><span className="sr-only">Rationale for {check.criterion.sc}</span><input value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Rationale or decision note" className="field" /></label>
        <Button type="button" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save"}</Button>
      </div>
      <details className="mt-3"><summary className="cursor-pointer text-sm font-semibold text-umich-blue">Evidence notes ({check.evidence.length})</summary><div className="mt-2 space-y-2 text-sm text-fg-muted">{check.evidence.map((item) => <p key={item.id} className="rounded-xs bg-surface-muted p-2">{item.note}</p>)}<div className="flex flex-wrap gap-2"><label className="min-w-64 flex-1"><span className="sr-only">Evidence note for {check.criterion.sc}</span><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add an evidence note" className="field" /></label><Button type="button" onClick={() => addEvidence.mutate()} disabled={!note.trim() || addEvidence.isPending}>Add evidence</Button></div></div></details>
    </Card>
  );
}
