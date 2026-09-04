import type { AlfaEvidenceDisplay } from "../api/types";

/** Manual instructions and missing-data notices share wording on every evidence view. */
export default function AlfaEvidenceNote({ evidence }: { evidence: AlfaEvidenceDisplay }) {
  const status = evidence.engine_evidence_status;
  return <>
    {evidence.manual_review_hint && <p className="mt-2 text-sm"><strong>How to verify:</strong> {evidence.manual_review_hint}</p>}
    {status && status !== "complete" && <p className="mt-2 text-sm text-fg-muted"><strong>Incomplete evidence.</strong> {status === "recovered" ? "Only complete diagnostic text could be recovered from this historical report." : status === "unavailable" ? "The original engine diagnostic is unavailable." : "The stored diagnostic was shortened; additional engine details are unavailable."}</p>}
  </>;
}
