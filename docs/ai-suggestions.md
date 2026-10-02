# AI fix suggestions

Axcess can ask a local AI model to suggest a fix for one
[occurrence](./glossary.md#occurrence). This page explains how to turn it on,
what it does with your data, and what it cannot do.

**In short:** it is off unless you turn it on. It runs only on this computer,
through Ollama. It can be wrong, so a person checks every suggestion before
using it. It never changes your site or your report.

## What you see

On a page's details, each occurrence has a **Suggest a fix (AI)** button.
Images get one too, when the scan found a problem with the image. Press it,
and the suggestion waits in a queue, then appears in the same card.

The Page inspector has the same button. It is in its own row under the
saved copy's toolbar, below the facts about the flagged element you are on.
Move to another element with Previous or Next, and the row shows that
element's suggestion.

Each suggestion sits in its own tinted box with a thick left border, so it
is never mistaken for what the scan found. It is brief on purpose:

| Part | What it is |
| --- | --- |
| For developers | **Before**: the element code (HTML) the scan found. For an image, Axcess reads it from the saved copy of the page. If the scan kept no element code (for example, a check of the whole page), "Before" says so. **After**: the suggested element code, and any CSS. When there is no code, a short explanation instead. |
| For content editors | Short steps to follow in your content system, and text to paste, such as alt text. Text already in a step is not repeated. |
| Rule check result | Shown only when it ran. For some rule check (axe) issues, Axcess runs that one rule on the suggested code. A pass means only that one rule passed. It does not show that the page meets WCAG. |
| About this suggestion | Closed by default. What to check by hand, whether a rule check could run, which model wrote it and when, and that it is not included in exports. |
| Helpful / Not helpful | Your answer is saved with the suggestion, to help judge the model. |

The warning "It can be wrong. Check it before you use it." is always shown.

The view that opens first follows the issue's "Who fixes it": content editors
for text and images, developers for code.

## How it works

```mermaid
flowchart LR
  A[Person presses<br/>Suggest a fix] --> B[API checks:<br/>turned on, report finished,<br/>not a sign-in report,<br/>occurrence is in this report]
  B --> C[(fix_suggestions<br/>queued)]
  C --> D[Background worker<br/>one at a time]
  D --> E[Build evidence from<br/>this report only,<br/>remove secrets]
  E --> F[Ollama on this computer]
  F --> G{Answer safe and<br/>in the right shape?}
  G -- no --> H[Saved as failed,<br/>never shown]
  G -- yes --> I[Run one axe rule on<br/>suggested code, offline]
  I --> J[(ready)]
  J --> K[Card shows it]
```

- Suggestions run one at a time, in the background. A running scan shares the
  same computer, so it can slow them down.
- The evidence sent to the model comes from one report only: the issue, the
  element code, the text near it, and for some checks the screenshot or image.
  Form values, email addresses, and tokens are removed first.
- Text from the scanned site is marked as data, not instructions. A page that
  says "ignore your rules" cannot change what the model is told to do.
- An answer that contains code that could run (a script, an event handler, a
  `javascript:` link) is refused and never shown.
- The rule check runs in a browser with no network access, on the suggested
  code alone.

## Turn it on

**In the desktop app** AI fix suggestions are already on. You only need
Ollama and the model (steps 1 and 2). Until they are there, the button's
place shows what is missing and the command to fix it. Axcess never
downloads a model by itself. To turn suggestions off, set
`AUDIT_SUGGESTIONS_ENABLED=false` before you start the app.

**In the web version** follow all four steps.

1. Install [Ollama](https://ollama.com) and start it.
2. Install the models. The vision model is optional; without it, image
   suggestions use the text model and do not look at the picture.

   ```bash
   ollama pull qwen2.5-coder:7b-instruct
   ollama pull qwen2.5vl:7b
   ```

3. Update the database: `make migrate`.
4. Set these, then restart Axcess:

| Setting | Default | What it does |
| --- | --- | --- |
| `AUDIT_SUGGESTIONS_ENABLED` | `false` (`true` in the desktop app) | Turns the feature on. |
| `AUDIT_SUGGESTION_TEXT_MODEL` | `qwen2.5-coder:7b-instruct` | Model for all suggestions. |
| `AUDIT_SUGGESTION_VISION_MODEL` | `qwen2.5vl:7b` | Model used when a picture helps (images, contrast, focus). |
| `AUDIT_SUGGESTION_TIMEOUT_S` | `120` | Longest wait for one answer, 10 to 600 seconds. |
| `AUDIT_SUGGESTION_QUEUE_MAX` | `20` | Most suggestions waiting at once, 1 to 200. |
| `AUDIT_OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama is. Keep it on this computer. |

Axcess asks Ollama for the exact answer shape it checks (structured
output), caps the answer's length, and keeps the model loaded for 10
minutes after the last suggestion so the next one starts faster. Then
Ollama frees the memory.

These settings are separate from the models a scan uses, so changing them
never changes a finished report.

## Where it does not work

- **Sign-in reports.** Their evidence is protected and is never sent to a
  model, so there is no button.
- **Unfinished reports.** A running, failed, or stopped scan has no button.
- **Informational issues.** There is nothing to fix.

## What is stored

Each suggestion is saved in the `fix_suggestions` table with the report: the
answer, the models used, the prompt version, the rule check result, and your
Helpful / Not helpful answer. Axcess keeps the last 10 per occurrence.
Deleting a report deletes its suggestions. Suggestions are **not** included
in exports.

## When something goes wrong

| What you see | What to do |
| --- | --- |
| A note that suggestions cannot run | Start Ollama, install the model, or run `make migrate`, as the note says. |
| "The AI model took too long to answer" | Try again when no scan is running, or raise `AUDIT_SUGGESTION_TIMEOUT_S`. |
| "An answer Axcess could not use safely" | Press **Try again**. If it keeps happening, try another model. |
| "Axcess restarted before the suggestion was finished" | Press **Try again**. |

## Measuring the model

`make suggest-eval` runs the prompt on a small set of made-up cases
(`tests/quality/suggest/cases_v1.yaml`) with your local model and prints how
many answers were usable and how many passed the rule check. It fails if any
answer contained code that could run. Run it after changing the prompt
(`src/audit/suggest/prompts/`) or the model.

## For developers

The code is in `src/audit/suggest/`:

| File | Job |
| --- | --- |
| `service.py` | Request rules and refusals; called by thin routes in `web/server.py`. |
| `context.py` | Builds the evidence from one report and removes secrets. |
| `provider.py` | Prompt, Ollama calls, and the answer's safety check. |
| `verify.py` | Runs one axe rule on the suggested code, offline. |
| `queue.py` | The background worker. |
| `repo.py` | SQL for `fix_suggestions` (migration `0030`). |

The API is `GET /api/suggestions/status`, `POST /api/scans/{id}/suggestions`,
`GET /api/scans/{id}/suggestions/{sid}`,
`GET /api/scans/{id}/occurrences/{kind}/{oid}/suggestion`, and `POST` to
`.../{sid}/cancel` and `.../{sid}/feedback`. Tests are in
`tests/ui/test_fix_suggestions.py` and `tests/ui/test_fix_suggestion_ui.py`.
