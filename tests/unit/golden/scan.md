# Accessibility evidence inventory — Scan #1

_Generated 2026-04-22 12:00 UTC by Axcess._

> This is a raw, status-bearing evidence inventory, including review leads and informational records. Use the stakeholder audit export for the expert-reviewed remediation worklist; neither artifact certifies conformance.

## Scan metadata

- **Seed URL:** http://example.com/
- **Status:** completed
- **Started:** 2026-04-22T12:00:00
- **Finished:** 2026-04-22T12:01:00
- **Pages crawled:** 2
- **Image-analysis evidence records:** 3
- **axe-core failed-rule evidence:** 0 (scanned 0 of 2 pages)
- **Siteimprove Alfa outcomes:** 0 failed; 0 need expert review (evaluated 0 of 2 pages)

## Executive summary

Retained 1 critical, 1 minor, 1 informational image-analysis evidence record(s) across the crawled pages. Status and expert review determine whether any record belongs in a remediation worklist.

| Severity | Count |
| --- | ---: |
| critical | 1 |
| major | 0 |
| minor | 1 |
| info | 1 |

## Top 3 image-analysis records

### [critical] Finding #1 — priority 9.10
- **Review status:** new
- **Classification:** essential
- **Alt adequacy:** missing
- **Image:** http://example.com/banner.png
- **OCR text:** 'BUY WIDGETS NOW'
- **VLM rationale:** Promotional banner with text as image.
- **Detector suggestion (verify before action):** This image contains essential text but has no alt attribute. Replace it with real HTML text or add alt="" plus visible text on the page. Minimum: set alt to the image's full visible text.
- **Occurrences:** 2
  - http://example.com/ — alt='(missing)' — above fold
  - http://example.com/about — alt='(missing)'
- **Review:** http://127.0.0.1:8765/findings/1

### [minor] Finding #3 — priority 3.69
- **Review status:** new
- **Alt adequacy:** missing
- **Image:** inline-svg://http://example.com/#0
- **Detector suggestion (verify before action):** Image contains text but has no alt attribute. Add alt conveying the image's text, or mark it decorative with alt="".
- **Occurrences:** 1
  - http://example.com/ — alt='(missing)'
- **Review:** http://127.0.0.1:8765/findings/3

### [info] Finding #2 — priority 1.69
- **Review status:** new
- **Classification:** logo
- **Alt adequacy:** adequate
- **Image:** http://example.com/logo.png
- **OCR text:** 'Acme Corp'
- **VLM rationale:** Brand mark.
- **Detector suggestion (verify before action):** Good — logo alt names the brand. No action required.
- **Occurrences:** 1
  - http://example.com/ — alt='Acme Corp'
- **Review:** http://127.0.0.1:8765/findings/2

## All image-analysis evidence

| # | Status | Severity | Score | Classification | Adequacy | Image |
| ---: | --- | --- | ---: | --- | --- | --- |
| 1 | new | critical | 9.10 | essential | missing | http://example.com/banner.png |
| 3 | new | minor | 3.69 | — | missing | inline-svg://http://example.com/#0 |
| 2 | new | info | 1.69 | logo | adequate | http://example.com/logo.png |
