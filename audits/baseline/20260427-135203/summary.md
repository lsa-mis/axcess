# Baseline a11y scan — raw axe-core results

Tags scanned: `wcag2a, wcag2aa, wcag2aaa, wcag21a, wcag21aa, wcag22aa, best-practice` (includes WCAG 2.2 AAA, the actual transformation target).

## Per-route counts

| UI | Route | Violations | Error |
|----|-------|-----------:|-------|
| spa | `/app/` | 1 |  |
| spa | `/app/scans` | 2 |  |
| spa | `/app/scans/new` | 1 |  |
| spa | `/app/scans/1` | 1 |  |
| spa | `/app/scans/1/findings` | 2 |  |
| jinja | `/scans` | 1 |  |
| jinja | `/scans/new` | 2 |  |
| jinja | `/scans/1` | 1 |  |
| jinja | `/scans/1/findings` | 1 |  |
| jinja | `/pages/1` | 1 |  |

## Unique rules failed (across all routes)

| Rule | Impact | Nodes | Tags | Help |
|------|--------|------:|------|------|
| `color-contrast-enhanced` | serious | 60 | wcag2aaa, wcag146 | [Elements must meet enhanced color contrast ratio thresholds](https://dequeuniversity.com/rules/axe/4.10/color-contrast-enhanced?application=axeAPI) |
| `color-contrast` | serious | 13 | wcag2aa, wcag143 | [Elements must meet minimum color contrast ratio thresholds](https://dequeuniversity.com/rules/axe/4.10/color-contrast?application=axeAPI) |
| `target-size` | serious | 5 | wcag22aa, wcag258 | [All touch targets must be 24px large, or leave sufficient space](https://dequeuniversity.com/rules/axe/4.10/target-size?application=axeAPI) |