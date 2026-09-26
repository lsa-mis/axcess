import type { AlfaEvidenceDisplay } from "../api/types";

/** Manual instructions and missing-data notices share wording on every evidence view. */
export default function AlfaEvidenceNote({ evidence }: { evidence: AlfaEvidenceDisplay }) {
  const status = evidence.engine_evidence_status;
  return <>
    {evidence.manual_review_hint && <p className="mt-2 text-sm"><strong>How to confirm it by hand:</strong> {evidence.manual_review_hint}</p>}
    {status && status !== "complete" && <p className="mt-2 text-sm text-fg-muted"><strong>Some details are missing.</strong> {status === "recovered" ? "This is an older report, so Axcess could recover only the complete parts of the rule check's message." : status === "unavailable" ? "The rule check's original message is not available." : "Axcess saved a shortened copy of the rule check's message. The rest of the details are not available."}</p>}
  </>;
}
