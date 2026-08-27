# Detection efficacy and evaluation pipeline

Axcess measures detection quality as an evidence system, not as a claim that a
scan proves WCAG conformance. Deterministic engines may produce likely-barrier
findings. Browser probes, OCR/VLM, and semantic analyzers produce review leads
that require an accessibility expert to confirm or reject them.

## What is evaluated

| Dimension | Question | Current gate |
| --- | --- | --- |
| Efficacy | Are surfaced findings and review leads supported by the labeled reference answer? | False-discovery rate below 5% and recall of at least 80%, overall and for every detection layer. |
| Efficiency | Can the local evidence path ingest detector output and build the unified issue view without a major regression? | At least 100 findings stored per second and issue projection below 5 seconds on the reference workload. |
| Scale | Does evidence processing remain usable as the report grows? | Correct row counts at 100, 500, and 1,000 pages, with no more than 3x normalized per-finding slowdown from the smallest to largest workload. |

The efficacy corpus also requires at least 20 surfaced labels and five negative
controls per layer. These floors prevent a detector from passing by suppressing
everything or by relying on a tiny denominator.

### Metric definitions

- **Precision** is `TP / (TP + FP)`.
- **False-discovery rate (FDR)** is `FP / (TP + FP)`: the share of surfaced
  results that become report noise.
- **False-positive rate (FPR)** is `FP / (FP + TN)`: the statistical rate among
  negative controls. It is reported separately from FDR.
- **Recall** is `TP / (TP + FN)`.
- **Write throughput** is persisted detector observations divided by transaction
  time. Migration/setup time is excluded.
- **Projection latency** is the time required to group the stored evidence into
  the report's unified issue rows.
- **Normalized slowdown** compares seconds per finding at the largest and
  smallest workloads.

## Current evidence and limitations

The versioned corpus at
`tests/quality/corpora/detection_precision_v1.json` covers all report-facing
layers: axe, Alfa, behavioral probes, OCR/VLM, and semantic analysis. It records
the pipeline, rule, reference label, and the product disposition for every
sample. The same evaluation keeps model- and probe-backed results in the expert
review lane.

The bundled corpus is synthetic by construction. Its results are regression
evidence, not a real-world accuracy estimate or confidence bound. An external
efficacy claim requires a held-out, representative corpus labeled independently
by at least two accessibility experts, with adjudication, inter-rater agreement,
per-rule denominators, abstentions, and confidence intervals.

The efficiency and scale gates exercise the durable local evidence path:
SQLite writes followed by the same unified issue projection used by the report
UI. They do not yet measure network crawling, browser rendering, OCR latency, or
local-model inference. Those measurements require pinned hardware, browser and
model versions, warm/cold-run separation, and representative authorized sites;
mixing them into a shared CI runner would produce misleading thresholds.

## Running the pipeline

```bash
make detection-evals
```

The command writes machine-readable and human-readable reports to
`artifacts/detection-evals/report.json` and
`artifacts/detection-evals/report.md`. It exits non-zero when any efficacy,
efficiency, scale, or integrity gate fails.

The dedicated GitHub Actions workflow runs on relevant pull requests, pushes to
`main`, weekly schedules, and manual dispatches. It publishes both reports as a
workflow artifact and adds the Markdown report to the job summary.

Thresholds and workload sizes live in
`tests/quality/detection_eval_config.json`. Changes to a threshold, workload,
producer, prompt, model, or reference label should be reviewed like a test
contract: explain the reason, preserve prior results when comparisons matter,
and increment the applicable corpus or configuration version.

## Next evaluation increments

1. Add a governed, expert-labeled validation corpus separate from development
   fixtures.
2. Record confidence intervals and calibration by rule, framework, page type,
   language, and protected/public context.
3. Add pinned-runner browser benchmarks for crawl time, render time, probe time,
   peak memory, and evidence bytes per page.
4. Add pinned local-model benchmarks for OCR/VLM and semantic latency, resource
   use, abstention rate, and quality by model version.
5. Track longitudinal results rather than weakening a gate when a regression is
   inconvenient.
