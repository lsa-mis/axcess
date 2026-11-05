"""The form error check's labelled real pages (AGENTS.md, "real pages first").

One entry per judged form: the page, the form's name as the check reports
it (``FormResult.form``) and which one when a page has several with that
name, the verdict it should get, and why we believe it.

``expected``:
- ``fail``: the form fails SC 3.3.1 when sent empty.
- ``not fail``: it does not (it passes, or only the browser's own message
  shows). Scored as a negative; the exact non-failing outcome is not.
- ``disputed``: the source and what the page shows disagree. Listed, not
  scored, until an expert decides.

``basis``:
- ``source``: an outside source says so; ``note`` quotes it.
- ``seen``: no outside source; a person looked at the before and after
  screenshots (named in ``note``).

Left out: W3C's BAD "before" survey (w3.org) fails only when the scan
sends empty forms, and an outside site must not receive a test's forms; it
is checked offline in ``tests/integration/test_form_error_send_empty.py``.
Labelled 2026-11-05. The verdicts were looked at by the developer's agent,
not by accessibility experts: this is evidence, not validation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RealForm:
    id: str
    url: str
    form: str
    expected: str
    basis: str
    note: str
    nth: int = 0
    send: bool = False


_AU = (
    "Accessible University info page: 'It states that there are errors, "
    "but does not identify what those errors were.'"
)
_508 = "https://baselinealignment.section508.gov/testcases/"
_FERN = "github.com/Daymond-Blair/accessibility-audit-training-lab data/answer-keys/fernhill.json"
_SEEN = "seen: the before and after screenshots, 2026-11-04/05"

PAGES: list[RealForm] = [
    # ------------------------------------------------------------- fail
    RealForm(
        "au-before-uw",
        "https://www.washington.edu/accesscomputing/AU/before.html",
        "Submit",
        "fail",
        "source",
        _AU,
    ),
    RealForm(
        "au-before-openassessit",
        "https://openassessittoolkit.github.io/accessible_u/before_u.html",
        "Submit",
        "fail",
        "source",
        _AU + " (the updated copy; issues.html says the same)",
    ),
    RealForm(
        "s508-fail-2",
        "https://baselinealignment.section508.gov/testfiles/TF10/10.D-2-fail-2.html",
        "Submit",
        "fail",
        "source",
        _508 + "TC10.D-2-fail-2.html: 'The error notification does not appear on screen in text.'",
    ),
    RealForm(
        "s508-fail-3",
        "https://baselinealignment.section508.gov/testfiles/TF10/10.D-2-fail-3.html",
        "Submit",
        "fail",
        "source",
        _508
        + "TC10.D-2-fail-3.html: 'The error notification does not identify the input in error.'",
    ),
    RealForm(
        "fernhill-v14",
        "https://daymond-blair.github.io/accessibility-audit-training-lab/scenarios/fernhill/index.html?defects=V14",
        "Request tour",
        "fail",
        "source",
        _FERN + " V14: 'only turns the field borders red. There is no error text'",
    ),
    RealForm(
        "mackjudd-contact",
        "https://mackjudd.com/contact.html",
        "Send",
        "fail",
        "source",
        "github.com/mackjuddco/auditable-test-fixture CRITERIA.md: "
        "'3.3.1 ... Errors shown by red border only'",
    ),
    RealForm(
        "rsd-entrega-1",
        "https://luviuche.github.io/rsd-proyecto/entrega-1/contacto.html",
        "Enviar mensaje",
        "fail",
        "source",
        "github.com/luviuche/rsd-proyecto informes_mapa-errores.md C6: "
        "'Validación solo visual | 3.3.1'",
    ),
    RealForm(
        "a11y-fails-3-3",
        "https://karstenlenz.github.io/a11y-fails/wcag-exercises/3_3_input_assistance.html",
        "Beispiele",
        "fail",
        "seen",
        _SEEN + ": the Name field's border turns red, no text. The demo says only "
        "'intentionally bad accessibility'.",
    ),
    RealForm(
        "abide-radio-group",
        "https://get.foundation/sites/docs/abide.html",
        "Radio Group",
        "fail",
        "seen",
        _SEEN + ": radio and checkbox labels turn red, no text. Unstable: on some runs "
        "the page tries to send the form and it is not checked.",
    ),
    # --------------------------------------------------------- not fail
    RealForm(
        "au-after-uw",
        "https://www.washington.edu/accesscomputing/AU/after.html",
        "Desired major(s):",
        "not fail",
        "source",
        "Accessible University's fixed page.",
    ),
    RealForm(
        "fernhill-none",
        "https://daymond-blair.github.io/accessibility-audit-training-lab/scenarios/fernhill/index.html?defects=none",
        "Request tour",
        "not fail",
        "source",
        _FERN + ": defects=none, no defect switched on.",
    ),
    RealForm(
        "rsd-entrega-2",
        "https://luviuche.github.io/rsd-proyecto/entrega-2/contacto.html",
        "Tipo de servicio que necesita",
        "not fail",
        "source",
        "The project's second delivery, which fixes C3 and C6: text errors linked to each field.",
    ),
    *(
        RealForm(
            f"s508-all-pass-{n}",
            f"https://baselinealignment.section508.gov/testfiles/TF10/10.D-all-pass-{n}.html",
            "Validate Number",
            "not fail",
            "source",
            _508 + f"TC10.D-all-pass-{n}: expected 'Pass'.",
        )
        for n in (1, 2, 3)
    ),
    RealForm(
        "parsley-simple",
        "https://parsleyjs.org/doc/examples/simple.html",
        "validate",
        "not fail",
        "seen",
        _SEEN + ": text under each field.",
    ),
    *(
        RealForm(
            f"bootstrap-{n}",
            "https://getbootstrap.com/docs/5.3/forms/validation/",
            "Submit form",
            "not fail",
            "seen",
            _SEEN + ": invalid-feedback text.",
            nth=n,
        )
        for n in (0, 1)
    ),
    *(
        RealForm(
            f"primevue-{n}",
            "https://primevue.org/forms/",
            "Submit",
            "not fail",
            "seen",
            _SEEN + ": message text under each field.",
            nth=n,
        )
        for n in (0, 1)
    ),
    RealForm(
        "shadcn-submit",
        "https://ui.shadcn.com/docs/forms/react-hook-form",
        "Submit",
        "not fail",
        "seen",
        _SEEN + ": FormMessage text.",
    ),
    *(
        RealForm(
            f"shadcn-save-{n}",
            "https://ui.shadcn.com/docs/forms/react-hook-form",
            "Save",
            "not fail",
            "seen",
            _SEEN + ": FormMessage text.",
            nth=n,
        )
        for n in (0, 1, 2)
    ),
    RealForm(
        "shadcn-plan",
        "https://ui.shadcn.com/docs/forms/react-hook-form",
        "Subscription Plan",
        "not fail",
        "seen",
        _SEEN + ": FormMessage text.",
    ),
    *(
        RealForm(
            f"mantine-{n}",
            "https://mantine.dev/form/validation/",
            "Submit",
            "not fail",
            "seen",
            _SEEN + ": error text under each field.",
            nth=n,
        )
        for n in range(5)
    ),
    *(
        RealForm(
            f"react-aria-{n}",
            "https://react-spectrum.adobe.com/react-aria/Form.html",
            "Submit",
            "not fail",
            "seen",
            _SEEN + ".",
            nth=n,
        )
        for n in (0, 1)
    ),
    *(
        RealForm(
            f"abide-submit-{n}",
            "https://get.foundation/sites/docs/abide.html",
            "Submit",
            "not fail",
            "seen",
            _SEEN + ": form-error text.",
            nth=n,
        )
        for n in (0, 1)
    ),
    *(
        RealForm(
            f"atlassian-schema-{n}",
            "https://atlassian.design/components/form/examples",
            "Create schema",
            "not fail",
            "seen",
            _SEEN + ": error message text.",
            nth=n,
        )
        for n in (0, 1)
    ),
    RealForm(
        "atlassian-archive",
        "https://atlassian.design/components/form/examples",
        "Archive page",
        "not fail",
        "seen",
        _SEEN + ": the browser's own message.",
    ),
    # --------------------------------------------------------- disputed
    RealForm(
        "s508-fail-1",
        "https://baselinealignment.section508.gov/testfiles/TF10/10.D-2-fail-1.html",
        "Submit",
        "disputed",
        "source",
        _508 + "TC10.D-2-fail-1: fails because the message 'is not contained in a live region'; "
        "the visible text 'Error: not a number.' describes the error. Announcing it is SC 4.1.3.",
    ),
    RealForm(
        "saturn-viewing",
        "https://discoversaturn.site/property-detail.html",
        "Request Viewing",
        "disputed",
        "source",
        "github.com/nsquared-team/a11y-practice-saturn SEEDED-ISSUES.md: 'Form validation errors "
        "color-only + not associated | 1.4.1 / 3.3.1'; "
        "red text ('Required') shows under each field.",
    ),
]
