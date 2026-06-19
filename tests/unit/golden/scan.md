# Accessibility audit — Scan #1

_Generated 2026-04-22 12:00 UTC by Axcess._

## Scan metadata

- **Seed URL:** http://example.com/
- **Status:** completed
- **Started:** 2026-04-22T12:00:00
- **Finished:** 2026-04-22T12:01:00
- **Pages crawled:** 2
- **Image-of-text findings (WCAG 1.4.5):** 3
- **WCAG axe-core findings:** 0 (scanned 0 of 2 pages)

## Executive summary

Detected 1 critical, 1 minor, 1 informational finding(s) across the crawled pages.

| Severity | Count |
| --- | ---: |
| critical | 1 |
| major | 0 |
| minor | 1 |
| info | 1 |

## Top 3 findings

### [critical] Finding #1 — priority 9.10
- **Classification:** essential
- **Alt adequacy:** missing
- **Image:** http://example.com/banner.png
- **OCR text:** 'BUY WIDGETS NOW'
- **VLM rationale:** Promotional banner with text as image.
- **Suggested fix:** This image contains essential text but has no alt attribute. Replace it with real HTML text or add alt="" plus visible text on the page. Minimum: set alt to the image's full visible text.
- **Occurrences:** 2
  - http://example.com/ — alt='(missing)' — above fold
  - http://example.com/about — alt='(missing)'
- **Review:** http://127.0.0.1:8765/findings/1

### [minor] Finding #3 — priority 3.69
- **Alt adequacy:** missing
- **Image:** inline-svg://http://example.com/#0
- **Suggested fix:** Image contains text but has no alt attribute. Add alt conveying the image's text, or mark it decorative with alt="".
- **Occurrences:** 1
  - http://example.com/ — alt='(missing)'
- **Review:** http://127.0.0.1:8765/findings/3

### [info] Finding #2 — priority 1.69
- **Classification:** logo
- **Alt adequacy:** adequate
- **Image:** http://example.com/logo.png
- **OCR text:** 'Acme Corp'
- **VLM rationale:** Brand mark.
- **Suggested fix:** Good — logo alt names the brand. No action required.
- **Occurrences:** 1
  - http://example.com/ — alt='Acme Corp'
- **Review:** http://127.0.0.1:8765/findings/2

## All image-of-text findings

| # | Severity | Score | Classification | Adequacy | Image |
| ---: | --- | ---: | --- | --- | --- |
| 1 | critical | 9.10 | essential | missing | http://example.com/banner.png |
| 3 | minor | 3.69 | — | missing | inline-svg://http://example.com/#0 |
| 2 | info | 1.69 | logo | adequate | http://example.com/logo.png |
