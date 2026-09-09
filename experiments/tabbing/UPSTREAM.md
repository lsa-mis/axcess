# Source and attribution

This experiment builds on Harry's A11y Crawler experiment at
[`harryg02/a11y-crawler`, branch `tabbing`](https://github.com/harryg02/a11y-crawler/tree/tabbing).
The reference snapshot is commit **`6c40f7c714ab053e40a8e0d80d33f27812403f1b`**,
retrieved on 2026-09-08. References below use that commit so future branch changes
do not change the study being discussed.

## Published experiment

- [Study, including methods, results, and limitations](https://github.com/harryg02/a11y-crawler/blob/6c40f7c714ab053e40a8e0d80d33f27812403f1b/experiments/tabbing/STUDY.md)
- [Detector descriptions](https://github.com/harryg02/a11y-crawler/blob/6c40f7c714ab053e40a8e0d80d33f27812403f1b/experiments/tabbing/DETECTORS.md)
- [Published generated results](https://github.com/harryg02/a11y-crawler/blob/6c40f7c714ab053e40a8e0d80d33f27812403f1b/experiments/tabbing/results/results.md)
- [Mouse/keyboard trial implementation](https://github.com/harryg02/a11y-crawler/blob/6c40f7c714ab053e40a8e0d80d33f27812403f1b/experiments/tabbing/differential.ts)
- [Matrix runner and equivalent-control filter](https://github.com/harryg02/a11y-crawler/blob/6c40f7c714ab053e40a8e0d80d33f27812403f1b/tests/tabbing-experiment.spec.ts)
- [Original ground-truth labels](https://github.com/harryg02/a11y-crawler/blob/6c40f7c714ab053e40a8e0d80d33f27812403f1b/experiments/tabbing/fixtures/truth.json)

The upstream study reports 60 labeled targets across nine pages: 26 labeled
violations and 34 negatives. Its best published configuration reports 26 true
positives, one false positive, and no false negatives: 96.3% precision and 100%
recall. Those are **upstream measurements**, taken on its own supplied targets
in a single Chromium run at 1280 × 900. They are not Axcess results, measurements
of candidate discovery, or evidence of general accessibility conformance.

## Material included here

`fixtures/upstream/` contains byte-for-byte copies of the upstream fixture source
files, including their original `truth.json`. Their license is Apache-2.0;
[LICENSE.upstream](LICENSE.upstream) and [NOTICE.upstream](NOTICE.upstream)
retain the upstream license and attribution. These files do not change the
license of unrelated Axcess files.

Two files are added to the upstream fixture directory by Axcess:

- `react/app.js`: the generated production bundle of the unchanged `app.jsx`,
  with retained dependency license comments.
- `react/build.json`: versions and the build command for that bundle.

The bundle uses Axcess's locked React and esbuild dependencies, rather than
silently depending on a future npm install. Its bytes are included in
`fixtures/frozen-manifest.json`. Run `node experiments/tabbing/build-react.mjs`
to rebuild intentionally after installing the frontend dependencies. A changed
bundle requires a new versioned corpus; it must not replace the first study's
frozen input.

`fixtures/holdout/` consists of new Axcess fixtures. The combined
`fixtures/truth.json` retains the original upstream labels and adds independently
authored labels, cohort membership, and three viewport-dependent overrides for
the new cases. Detectors receive target identifiers but not the labels or notes.

## Label caveats

Original labels are retained for a comparable reference score, including two
interpretations that need care:

- **p33, hover-only tooltip:** upstream labels it a negative, reasoning that it
  belongs to 1.4.13 rather than 2.1.1. W3C's discussion of hover/focus content also
  links keyboard access to 2.1.1. We therefore describe the negative as an
  inherited, debatable label. A detector hit still counts as a false positive
  against that frozen label; it does not settle the normative question.
- **p63, console-only effect:** upstream labels a click handler that only logs
  to the console as a violation. An executed diagnostic statement does not by
  itself establish functionality that a user needs. Again, we preserve the label
  and disclose the assumption rather than silently changing the score.

Sources: [W3C Keyboard guidance](https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html)
and [W3C Content on Hover or Focus guidance](https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html).

## Collaboration protocol

Codex authored the additional fixtures and labels without reading Claude's Axcess
detector. Claude agreed not to inspect those fixtures or labels before the first
score. This was **independent authoring under an agreed no-reading protocol**;
both agents shared filesystem access. They had already discussed the upstream
weaknesses, so this was not an independent external evaluation. The protocol,
handoffs, and subsequent reviews are recorded in the repository's `LLMTalk`.

The frozen manifest records file hashes, the freeze time, source revision, probe
counts, and fixture validation. First-run results must be retained when later
implementation changes are evaluated on these now-known examples.
