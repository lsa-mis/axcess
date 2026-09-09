"""SC 3.3.1, Error Identification probe.

Deterministic, no model. The error state a screen-reader user meets only
exists *after* a form tries to validate, so the probe triggers each form's
client-side validation — but **never submits**:

  * It only acts on a form when ``form.checkValidity()`` is already false
    (there is at least one constraint-invalid control). A form with nothing
    invalid is skipped, so a valid single-field search box is never fired.
  * It calls ``form.reportValidity()``, which fires the browser's ``invalid``
    events (waking any custom validator that listens for them) and shows the
    native error UI, and which — unlike ``requestSubmit()`` — **never submits
    the form**, valid or not.
  * A capture-phase ``preventDefault`` submit listener is installed first, as
    defense in depth against a page handler that calls ``form.submit()``.

No network write, no navigation, no credentials. This is the same safety
boundary the interaction probe draws around destructive controls.

Then it asks one structural question per invalid control: now that an error
exists, is it identified in text and tied to the field? Two failures:

  * ``error-not-identified-in-text`` — the control is invalid and there is no
    error text anywhere a user could read (only a colour change, or nothing).
    Reported only for ``novalidate`` forms (the site opted out of the browser's
    own accessible messages and therefore owns the error UX).
  * ``error-not-programmatically-associated`` — a visible error message exists
    near the field but nothing links it to the control (no ``aria-invalid`` /
    ``aria-describedby`` / ``aria-errormessage``), so assistive technology
    never announces it.

Edge cases (server-only validation, purely visual cues a human must judge)
still need review; the coverage matrix marks this ``partial``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

from audit.analyzer.error_id.base import (
    RULE_NOT_ASSOCIATED,
    RULE_NOT_IDENTIFIED,
    ErrorIdentificationFinding,
)
from audit.logging import get_logger

log = get_logger(__name__)

# Cap forms per page and controls per form so a pathological page can't blow
# up the crawl. Most real pages have one or two forms.
MAX_FORMS = 20
MAX_CONTROLS = 60

# One round-trip: for every form that already has an invalid control, safely
# trigger reportValidity() (never submits) and return, per invalid control,
# the signals the Python classifier needs. The DOM is only *read* afterwards.
_TRIGGER_AND_COLLECT_JS = """
(caps) => {
  const [maxForms, maxControls] = caps;
  const cssPath = (el) => {
    if (el.id) return el.tagName.toLowerCase() + '#' + el.id;
    let p = el.tagName.toLowerCase();
    if (el.name) p += '[name="' + el.name + '"]';
    else if (el.className && typeof el.className === 'string') {
      const c = el.className.trim().split(/\\s+/)[0];
      if (c) p += '.' + c;
    }
    return p;
  };
  const results = [];
  const forms = Array.from(document.querySelectorAll('form')).slice(0, maxForms);
  for (const form of forms) {
    // Defense in depth: never let a submit escape, even if a page handler
    // calls form.submit() in response to the invalid events below.
    try {
      form.addEventListener('submit', (e) => e.preventDefault(), { capture: true });
    } catch (e) {}
    let anyInvalid = false;
    try { anyInvalid = form.checkValidity() === false; } catch (e) { continue; }
    if (!anyInvalid) continue;  // nothing invalid; never fire a valid form
    // reportValidity fires 'invalid' events + shows native UI; it NEVER submits.
    try { form.reportValidity(); } catch (e) {}
    const noValidate = form.noValidate === true;
    const controls = Array.from(form.elements || []).slice(0, maxControls);
    for (const el of controls) {
      if (!el || typeof el.willValidate === 'undefined') continue;
      if (!el.willValidate) continue;
      let invalid = false;
      try { invalid = el.validity && el.validity.valid === false; } catch (e) { continue; }
      if (!invalid) continue;
      const db = (el.getAttribute('aria-describedby') || '') + ' ' +
        (el.getAttribute('aria-errormessage') || '');
      const ids = db.trim().split(/\\s+/).filter(Boolean);
      let describedText = '';
      for (const id of ids) {
        const r = document.getElementById(id);
        if (r) describedText += ' ' + (r.textContent || '');
      }
      describedText = describedText.replace(/\\s+/g, ' ').trim().slice(0, 200);
      const ariaInvalid = (el.getAttribute('aria-invalid') || '').toLowerCase() === 'true';
      let container = null;
      try {
        container = el.closest('.field, .form-group, .form-control, .input, li, p, fieldset');
      } catch (e) {}
      container = container || el.parentElement;
      let nearbyErrorText = '';
      if (container) {
        const cands = container.querySelectorAll(
          '[role=alert], [aria-live], .error, .invalid, .help-block, ' +
          '.form-error, .field-error, .error-message'
        );
        for (const c of cands) {
          const t = (c.textContent || '').trim();
          if (t) nearbyErrorText += ' ' + t;
        }
      }
      nearbyErrorText = nearbyErrorText.replace(/\\s+/g, ' ').trim().slice(0, 200);
      results.push({
        selector: cssPath(el),
        html: (el.outerHTML || '').slice(0, 300),
        noValidate: noValidate,
        ariaInvalid: ariaInvalid,
        describedText: describedText,
        nearbyErrorText: nearbyErrorText,
      });
    }
  }
  return results;
}
"""


def classify(raw: list[Any]) -> list[ErrorIdentificationFinding]:
    """Map the JS-collected per-control signals to SC 3.3.1 findings.

    Pure function, no browser — the whole decision boundary lives here so it
    can be unit-tested with synthetic signal dicts. Conservative by design
    (the pipeline is a review lead, precision matters): only clear structural
    failures are emitted.
    """
    findings: list[ErrorIdentificationFinding] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        selector = str(item.get("selector") or "").strip()
        if not selector or selector in seen:
            continue
        html = str(item.get("html") or "")
        no_validate = bool(item.get("noValidate"))
        aria_invalid = bool(item.get("ariaInvalid"))
        described_text = str(item.get("describedText") or "").strip()
        nearby_error_text = str(item.get("nearbyErrorText") or "").strip()

        # Programmatic text association: a described-by/errormessage element
        # with text, or aria-invalid paired with any readable error text.
        associated = bool(described_text) or (aria_invalid and bool(nearby_error_text))
        if associated:
            continue  # error is identified AND tied to the field — conforming

        if no_validate and not described_text and not nearby_error_text:
            # The site turned off native validation (owns the error UX) yet an
            # invalid control has no error text at all.
            seen.add(selector)
            findings.append(
                ErrorIdentificationFinding(
                    rule_id=RULE_NOT_IDENTIFIED,
                    target_selector=selector,
                    failure_summary=(
                        "This form disables native browser validation (novalidate) and this "
                        "control is invalid, but no error is presented in text — a screen-reader "
                        "user is given no way to know what is wrong or how to fix it."
                    ),
                    html_snippet=html,
                    help=(
                        'When validation fails, show a text error, put aria-invalid="true" on '
                        "the control, and point aria-describedby (or aria-errormessage) at the "
                        "message so assistive technology announces it."
                    ),
                )
            )
        elif nearby_error_text and not aria_invalid and not described_text:
            # A visible error message exists but nothing links it to the field.
            seen.add(selector)
            findings.append(
                ErrorIdentificationFinding(
                    rule_id=RULE_NOT_ASSOCIATED,
                    target_selector=selector,
                    failure_summary=(
                        "A visible error message is shown near this control "
                        f'("{nearby_error_text[:80]}") but nothing ties it to the field: no '
                        "aria-invalid, aria-describedby, or aria-errormessage. Assistive "
                        "technology never announces the error."
                    ),
                    html_snippet=html,
                    help=(
                        'Add aria-invalid="true" to the control and reference the error element '
                        "with aria-describedby (or aria-errormessage) so the message is "
                        "programmatically associated with the field."
                    ),
                )
            )
    return findings


@dataclass
class ErrorIdentificationProbe:
    """Runs the SC 3.3.1 error-identification check against a live page."""

    max_forms: int = MAX_FORMS
    max_controls: int = MAX_CONTROLS
    # The protected companion must not log browser exception text because it
    # can include an authenticated route or page-provided diagnostic.
    suppress_diagnostics: bool = False

    async def run(self, page: Page) -> list[ErrorIdentificationFinding]:
        """Trigger + inspect form validation. Never raises, never submits."""
        try:
            raw: Any = await page.evaluate(
                _TRIGGER_AND_COLLECT_JS, [self.max_forms, self.max_controls]
            )
        except Exception as exc:  # pragma: no cover - defensive
            if self.suppress_diagnostics:
                log.warning("error_id.probe_failed_in_protected_context")
            else:
                log.warning("error_id.probe_failed", error=str(exc))
            return []
        return classify(raw if isinstance(raw, list) else [])
