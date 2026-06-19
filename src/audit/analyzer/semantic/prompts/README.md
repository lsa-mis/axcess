# Per-criterion prompt templates

One `.txt` file per WCAG SC the semantic pipeline targets.

## Naming

`sc_<n>_<n>_<n>_<short_slug>.txt` — for example
`sc_2_4_4_link_purpose_in_context.txt`. The leading underscore-separated
numbers match the SC dotted form (`2.4.4`) so the runner can resolve
the file from the criterion the analyzer is built for.

## Shape

Each template should contain:

1. **System framing** — one sentence telling the model it's an
   accessibility expert evaluating one specific WCAG SC.
2. **The SC itself** — title, level, one-paragraph description.
3. **Common failures** — pulled from the WCAG docs for that SC.
4. **Test rules** — concrete checks the model should perform.
5. **Input placeholder** — `{elements}` is replaced by the extractor's
   per-criterion output (typically a JSON-ish list of element dicts).
6. **Output schema** — the JSON shape the runner will parse. Always
   include `overall_violation` (`"yes"` / `"no"`) and
   `violated_elements` (list of `{selector, reason, recommendation}`).

The runner uses Ollama's `format=json` mode, so the model is
constrained to valid JSON — but the schema can drift, so the runner
also validates against an expected shape and drops malformed rows.

## Prompt versioning

The runner content-hashes each filled prompt and stores the hash as
the row's `prompt_version` in `analyses.model_versions_json`. So
editing a `.txt` here produces new prompt versions in the DB on the
next scan — making "did this rule's wording change since last week?"
answerable from the data.

## Adding a new SC

1. Write `sc_<n>_<n>_<n>_<slug>.txt` here.
2. Add an entry to `src/audit/rules/audit_report.yaml` with the
   what/why/how cards (these double as the report copy AND inform
   the prompt's "common failures" section).
3. Add the per-criterion analyzer in `src/audit/analyzer/semantic/`
   (one class per SC, implements the `SemanticAnalyzer` protocol).
4. Add the SC code to the default `semantic_criteria` list in
   `src/audit/config.py`.
5. Write a unit test + an HTML fixture page with deliberate violations.
