"""AI fix suggestions: on-demand, per-occurrence advice from a local model.

A person asks for a suggestion on one occurrence (one element on one page).
Axcess builds a small, redacted bundle of that occurrence's stored evidence,
asks the local Ollama model for a JSON answer, validates it, re-runs the rule
check on suggested HTML where it can, and saves the result beside the report.

Boundaries this package keeps:

* Off by default (``AUDIT_SUGGESTIONS_ENABLED``). Its models are separate
  from the scan-analysis models, so a finished report never changes.
* Local only. Evidence goes to the Ollama daemon and nowhere else.
* Read-only towards the report. Suggestions never change a finding, status,
  issue group or export; the model has no tools and cannot act.
* One report at a time. Every request names a ``scan_id`` and the service
  checks that the occurrence belongs to it.
* Protected (signed-in) reports are refused: their evidence is encrypted and
  their AI runs only on the companion computer.
"""
