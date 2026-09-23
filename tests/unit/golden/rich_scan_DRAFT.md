> **DRAFT, INCOMPLETE ACCESSIBILITY EVALUATION**
>
> Evaluation status: **in progress**. This export was explicitly downloaded as a draft. Expert review is incomplete; do not treat it as a conformance determination.

# Accessibility evidence inventory, Scan #1

_Generated 2026-04-22 12:00 UTC by Axcess._

> This is a raw, status-bearing evidence inventory, including review leads and informational records. Use the stakeholder audit export for the expert-reviewed remediation worklist; neither artifact certifies conformance.

## Scan metadata

- **Seed URL:** https://example.org/
- **Status:** completed
- **Started:** 2026-04-22T12:00:00
- **Finished:** 2026-04-22T12:30:00
- **Pages crawled:** 5
- **Image-analysis evidence records:** 4
- **axe-core failed-rule evidence:** 74 (scanned 5 of 5 pages)
- **Siteimprove Alfa outcomes:** 1 failed; 1 need expert review (evaluated 2 of 5 pages)
- **Errors:** 1

## Executive summary

Retained 1 critical, 2 minor, 1 informational image-analysis evidence record(s) across the crawled pages. Status and expert review determine whether any record belongs in a remediation worklist.

| Severity | Count |
| --- | ---: |
| critical | 1 |
| major | 0 |
| minor | 2 |
| info | 1 |

## Top 4 image-analysis records

### [critical] Finding #1, priority 9.10
- **Review status:** new
- **Classification:** essential
- **Alt adequacy:** missing
- **Image:** https://example.org/banner.png
- **OCR text:** 'BUY WIDGETS NOW'
- **VLM rationale:** Promotional banner with text as image.
- **Detector suggestion (verify before action):** This image contains essential text but has no alt attribute. Replace it with real HTML text or add alt="" plus visible text on the page. Minimum: set alt to the image's full visible text.
- **Occurrences:** 2
  - https://example.org/, alt='(missing)', above fold
  - https://example.org/about, alt='(missing)'
- **Review:** http://127.0.0.1:8765/findings/1

### [minor] Finding #3, priority 3.69
- **Review status:** new
- **Alt adequacy:** missing
- **Image:** https://example.org/hours.png
- **OCR text:** 'OPEN DAILY 9-5'
- **Detector suggestion (verify before action):** Image contains text but has no alt attribute. Add alt conveying the image's text, or mark it decorative with alt="".
- **Occurrences:** 1
  - https://example.org/contact, alt='(missing)'
- **Review:** http://127.0.0.1:8765/findings/3

### [minor] Finding #4, priority 3.10
- **Review status:** new
- **Alt adequacy:** adequate
- **Image:** inline-svg://https://example.org/#0
- **Detector suggestion (verify before action):** Alt is missing or doesn't match the image's visible text. Update it to reflect the text in the image.
- **Occurrences:** 2
  - https://example.org/blog, alt='Company\rlogo'
  - https://example.org/, alt='Company\rlogo'
- **Review:** http://127.0.0.1:8765/findings/4

### [info] Finding #2, priority 1.69
- **Review status:** new
- **Classification:** logo
- **Alt adequacy:** adequate
- **Image:** https://example.org/logo.png
- **OCR text:** 'Acme Corp'
- **VLM rationale:** Brand mark.
- **Detector suggestion (verify before action):** Good, logo alt names the brand. No action required.
- **Occurrences:** 1
  - https://example.org/, alt='Acme Corp'
- **Review:** http://127.0.0.1:8765/findings/2

## All image-analysis evidence

| # | Status | Severity | Score | Classification | Adequacy | Image |
| ---: | --- | --- | ---: | --- | --- | --- |
| 1 | new | critical | 9.10 | essential | missing | https://example.org/banner.png |
| 3 | new | minor | 3.69 | n/a | missing | https://example.org/hours.png |
| 4 | new | minor | 3.10 | n/a | adequate | inline-svg://https://example.org/#0 |
| 2 | new | info | 1.69 | logo | adequate | https://example.org/logo.png |

## WCAG DOM-engine findings

axe-core found 74 violation(s) across 5 page(s); Siteimprove Alfa returned 1 failed outcome(s) and 1 expert-review lead(s) across 2 page(s).

| WCAG level | Count |
| --- | ---: |
| A | 45 |
| AA | 29 |
| AAA | 1 |
| best-practice | 5 |

**Scope reminder.** Each finding records its source. axe-core and Siteimprove Alfa are complementary automated methods, not conformance verdicts. Alfa `cantTell` outcomes are explicitly expert-review leads; manual evaluation remains required.

### Top 30 DOM-engine findings

### [critical] fixture-rule-12, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 12 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-12`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-12
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-41

### [critical] fixture-rule-20, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 20 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-20`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-20
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-52

### [critical] fixture-rule-24, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 24 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-24`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-24
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-57

### [critical] fixture-rule-36, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 36 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-36`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-36
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-73

### [critical] image-alt, SC 1.1.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Images must have alternative text
- **Page:** https://example.org/
- **Target:** `main > img.banner`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/image-alt
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-5

### [critical] keyboard-trap-stuck, SC 2.1.2 (Level A)
- **Source:** Keyboard probe
- **Outcome:** Needs expert review (observed lead)
- **Rule:** Keyboard users must be able to leave the component.
- **Page:** https://example.org/
- **Target:** `#menu-trap`
- **Why it failed:** Measured focus exit behavior: 4 Tab attempts and 4 Shift+Tab attempts remained on #menu-trap (8 failed exit attempts total).
- **Docs:** https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-78

### [critical] fixture-rule-12, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 12 synthetic check
- **Page:** https://example.org/about
- **Target:** `#fixture-12`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-12
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/2#finding-42

### [critical] fixture-rule-16, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 16 synthetic check
- **Page:** https://example.org/about
- **Target:** `#fixture-16`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-16
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/2#finding-47

### [critical] fixture-rule-24, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 24 synthetic check
- **Page:** https://example.org/about
- **Target:** `#fixture-24`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-24
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/2#finding-58

### [critical] fixture-rule-36, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 36 synthetic check
- **Page:** https://example.org/about
- **Target:** `#fixture-36`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-36
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/2#finding-74

### [critical] fixture-rule-04, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 04 synthetic check
- **Page:** https://example.org/blog
- **Target:** `#fixture-04`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-04
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/5#finding-31

### [critical] fixture-rule-32, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 32 synthetic check
- **Page:** https://example.org/contact
- **Target:** `#fixture-32`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-32
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/3#finding-68

### [critical] label, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Barrier confirmed by expert, risk accepted
- **Rule:** Form elements must have labels
- **Page:** https://example.org/contact
- **Target:** `input[type=text]`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/label
- **Status:** accepted_risk
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/3#finding-18

### [critical] fixture-rule-08, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 08 synthetic check
- **Page:** https://example.org/products
- **Target:** `#fixture-08`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-08
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/4#finding-36

### [critical] fixture-rule-28, SC 1.3.1 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 28 synthetic check
- **Page:** https://example.org/products
- **Target:** `#fixture-28`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-28
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/4#finding-63

### [serious] color-contrast, SC 1.4.3 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Elements must meet minimum color contrast
- **Page:** https://example.org/
- **Target:** `p > span.muted`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/color-contrast
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-1

### [serious] color-contrast, SC 1.4.3 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Elements must meet minimum color contrast
- **Page:** https://example.org/
- **Target:** `footer small`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/color-contrast
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-2

### [serious] fixture-rule-05, SC 2.4.7 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 05 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-05`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-05
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-32

### [serious] fixture-rule-09, SC 2.4.7 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 09 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-09`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-09
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-37

### [serious] fixture-rule-21, SC 2.4.7 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 21 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-21`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-21
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-53

### [serious] fixture-rule-25, SC 2.4.7 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 25 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-25`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-25
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-59

### [serious] fixture-rule-33, SC 2.4.7 (Level AA)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Fixture rule 33 synthetic check
- **Page:** https://example.org/
- **Target:** `#fixture-33`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/fixture-rule-33
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-69

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(1)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-6

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(2)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-7

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(3)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-8

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(4)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-9

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(5)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-10

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(6)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-11

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(7)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-12

### [serious] link-name, SC 4.1.2 (Level A)
- **Source:** axe-core
- **Outcome:** Failed automated rule outcome
- **Rule:** Links must have discernible text
- **Page:** https://example.org/
- **Target:** `nav > a:nth-child(8)`
- **Why it failed:** Fix any of the following: the rule's check failed.
- **Docs:** https://dequeuniversity.com/rules/axe/4.10/link-name
- **Status:** new
- **Review:** http://127.0.0.1:8765/app/scans/1/pages/1#finding-13

### All DOM-engine findings

| # | Source | Outcome | Impact | WCAG SC | Level | Rule | Page |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 41 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-12` | https://example.org/ |
| 52 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-20` | https://example.org/ |
| 57 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-24` | https://example.org/ |
| 73 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-36` | https://example.org/ |
| 5 | axe-core | Failed automated rule outcome | critical | 1.1.1 | A | `image-alt` | https://example.org/ |
| 78 | Keyboard probe | Needs expert review (observed lead) | critical | 2.1.2 | A | `keyboard-trap-stuck` | https://example.org/ |
| 42 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-12` | https://example.org/about |
| 47 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-16` | https://example.org/about |
| 58 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-24` | https://example.org/about |
| 74 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-36` | https://example.org/about |
| 31 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-04` | https://example.org/blog |
| 68 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-32` | https://example.org/contact |
| 18 | axe-core | Barrier confirmed by expert, risk accepted | critical | 4.1.2 | A | `label` | https://example.org/contact |
| 36 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-08` | https://example.org/products |
| 63 | axe-core | Failed automated rule outcome | critical | 1.3.1 | A | `fixture-rule-28` | https://example.org/products |
| 1 | axe-core | Failed automated rule outcome | serious | 1.4.3 | AA | `color-contrast` | https://example.org/ |
| 2 | axe-core | Failed automated rule outcome | serious | 1.4.3 | AA | `color-contrast` | https://example.org/ |
| 32 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-05` | https://example.org/ |
| 37 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-09` | https://example.org/ |
| 53 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-21` | https://example.org/ |
| 59 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-25` | https://example.org/ |
| 69 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-33` | https://example.org/ |
| 6 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 7 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 8 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 9 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 10 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 11 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 12 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 13 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 14 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 15 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 16 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 17 | axe-core | Failed automated rule outcome | serious | 4.1.2 | A | `link-name` | https://example.org/ |
| 3 | axe-core | Failed automated rule outcome | serious | 1.4.3 | AA | `color-contrast` | https://example.org/about |
| 19 | axe-core | Failed automated rule outcome | serious | 1.4.6 | AAA | `color-contrast-enhanced` | https://example.org/about |
| 27 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-01` | https://example.org/about |
| 38 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-09` | https://example.org/about |
| 54 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-21` | https://example.org/about |
| 70 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-33` | https://example.org/about |
| 64 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-29` | https://example.org/blog |
| 4 | axe-core | Reviewed, not a barrier | serious | 1.4.3 | AA | `color-contrast` | https://example.org/contact |
| 48 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-17` | https://example.org/contact |
| 43 | axe-core | Failed automated rule outcome | serious | 2.4.7 | AA | `fixture-rule-13` | https://example.org/products |
| 25 | axe-core | Failed automated rule outcome | moderate | 1.3.1 | A | `fixture-empty-help` | https://example.org/ |
| 33 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-06` | https://example.org/ |
| 39 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-10` | https://example.org/ |
| 49 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-18` | https://example.org/ |
| 65 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-30` | https://example.org/ |
| 20 | axe-core | Failed automated rule outcome | moderate | n/a | n/a | `page-has-heading-one` | https://example.org/ |
| 75 | Semantic analyzer | Needs expert review (observed lead) | moderate | 2.4.4 | A | `semantic:2.4.4` | https://example.org/ |
| 34 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-06` | https://example.org/about |
| 50 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-18` | https://example.org/about |
| 60 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-26` | https://example.org/about |
| 66 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-30` | https://example.org/about |
| 21 | axe-core | Failed automated rule outcome | moderate | n/a | n/a | `page-has-heading-one` | https://example.org/about |
| 76 | Semantic analyzer | Needs expert review (observed lead) | moderate | 2.4.4 | A | `semantic:2.4.4` | https://example.org/about |
| 26 | axe-core | Failed automated rule outcome | moderate | 1.3.1 | A | `fixture-empty-help` | https://example.org/blog |
| 44 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-14` | https://example.org/blog |
| 71 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-34` | https://example.org/blog |
| 24 | axe-core | Failed automated rule outcome | moderate | n/a | n/a | `region` | https://example.org/blog |
| 28 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-02` | https://example.org/contact |
| 55 | axe-core | Failed automated rule outcome | moderate | 3.3.2 | A | `fixture-rule-22` | https://example.org/contact |
| 77 | Semantic analyzer | Barrier confirmed by expert, remediation planned | moderate | 2.4.4 | A | `semantic:2.4.4` | https://example.org/contact |
| 22 | axe-core | Failed automated rule outcome | moderate | n/a | n/a | `page-has-heading-one` | https://example.org/products |
| 23 | axe-core | Failed automated rule outcome | moderate | n/a | n/a | `region` | https://example.org/products |
| 29 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-03` | https://example.org/ |
| 45 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-15` | https://example.org/ |
| 61 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-27` | https://example.org/ |
| 72 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-35` | https://example.org/ |
| 30 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-03` | https://example.org/about |
| 40 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-11` | https://example.org/about |
| 46 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-15` | https://example.org/about |
| 62 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-27` | https://example.org/about |
| 67 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-31` | https://example.org/about |
| 51 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-19` | https://example.org/blog |
| 35 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-07` | https://example.org/contact |
| 56 | axe-core | Failed automated rule outcome | minor | 2.5.8 | AA | `fixture-rule-23` | https://example.org/products |
| 79 | Siteimprove Alfa | Failed automated rule outcome | n/a | 1.1.1 | A | `sia-r2` | https://example.org/ |
| 80 | Siteimprove Alfa | Needs expert review (Alfa cantTell) | n/a | 2.5.8 | AA | `sia-r111` | https://example.org/about |
