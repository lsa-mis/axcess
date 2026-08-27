# Axcess detector quality benchmark

`corpora/detection_precision_v1.json` is a frozen, versioned set of detector
outputs and binary reference labels. Its purpose is to catch precision
regressions and keep every detection layer visible in quality discussions.

The root-level [`DETECTION_EFFICACY.md`](../../DETECTION_EFFICACY.md) defines
the combined efficacy, efficiency, and scale pipeline. Run `make
detection-evals` to produce its Markdown and JSON reports; `make quality-gate`
remains the narrower corpus-only gate.

The quality gate uses the **false-discovery rate** (`FP / (TP + FP)`): the
share of surfaced findings or review leads that are not barriers. That is the
report-noise measure behind the product target of “less than 5% false
positives.” The report also shows the statistical false-positive rate
(`FP / (FP + TN)`) separately.

The bundled v1 corpus is synthetic by construction. Each named sample is a
small adversarial scenario whose reference answer follows from how the
fixture is defined. This makes it useful for repeatable regression testing,
but it does **not** establish real-world accuracy. In particular, a 0% point
estimate on this corpus is not a 0% expected production rate and is not a
confidence bound.

The expected report dispositions are part of the gate. axe failures may enter
the likely-barrier lane. Alfa `failed` outcomes may do the same while
`cantTell` remains a review lead. Browser-behavior probes, OCR/VLM evidence,
and semantic-model evidence must remain expert-review leads even when the
synthetic reference fixture is known to contain a barrier.

Before Axcess makes an external accuracy claim, add a separately governed
validation corpus that:

- samples representative U-M public and authorized protected applications;
- includes modern frameworks, dynamic states, languages, content types, and
  assistive-technology workflows;
- is labeled independently by at least two accessibility experts, with
  disagreements adjudicated and inter-rater agreement recorded;
- is held out from prompt, probe, and threshold development; and
- reports confidence intervals, per-rule denominators, false negatives, and
  abstentions in addition to precision.

## Updating the corpus

Do not silently relabel a sample to make the gate pass. When a detector,
model, prompt, threshold, or expected disposition changes:

1. Reproduce the output against the named scenario.
2. Review the reference label without looking at the desired gate result.
3. Add a new sample or update the disposition and explain the scenario.
4. Increment `corpus_version` (and `schema_version` if the shape changes).
5. Run `make quality-gate` and inspect the rule-level diagnostics.
