"""Redaction of downloaded reports: what is removed, and what a fix still needs."""

from __future__ import annotations

import csv
import io
import json

import pytest
from openpyxl import Workbook, load_workbook

from audit.exports.redaction import (
    REDACTED,
    REDACTED_CARD,
    REDACTED_EMAIL,
    REDACTED_ID,
    REDACTED_ID_NUMBER,
    REDACTED_PHONE,
    REDACTION_CSV_COLUMN,
    REDACTION_NOTICE,
    REDACTION_TITLE,
    redact_evidence,
    redact_export,
    redact_field,
    redact_text,
    redact_url,
    scan_locators,
)

# --- Element code (HTML) -------------------------------------------------------


def test_form_field_value_is_redacted_and_the_rest_of_the_element_kept() -> None:
    html = '<input type="email" id="email" name="user" value="jane@example.com" class="field">'
    assert redact_text(html) == (
        '<input type="email" id="email" name="user" value="[redacted]" class="field">'
    )


def test_bare_and_single_quoted_values_are_redacted() -> None:
    assert redact_text("<input type=hidden name=csrf value=abc123>") == (
        '<input type=hidden name=csrf value="[redacted]">'
    )
    assert redact_text("<input value='4242'>") == "<input value='[redacted]'>"


def test_value_cut_short_by_the_scanner_is_still_redacted() -> None:
    assert redact_text('<input name="pin" value="12345') == '<input name="pin" value="[redacted]'


def test_empty_value_is_left_alone() -> None:
    assert redact_text('<input value="">') == '<input value="">'


def test_textarea_content_is_redacted() -> None:
    assert redact_text('<textarea id="n">My note to the bank</textarea>') == (
        '<textarea id="n">[redacted]</textarea>'
    )


def test_textarea_cut_short_before_its_closing_tag_is_redacted() -> None:
    # Element code is saved cut short, so the closing tag can be missing; the
    # typed text still must not survive.
    assert redact_text('<div><textarea id="n">My note to the bank, about my loan') == (
        '<div><textarea id="n">[redacted]'
    )


def test_secret_named_attributes_are_redacted_but_aria_values_kept() -> None:
    html = '<div data-session-id="s-991" data-value="x" nonce="r4nd" aria-valuenow="5">'
    assert redact_text(html) == (
        '<div data-session-id="[redacted]" data-value="[redacted]" nonce="[redacted]" '
        'aria-valuenow="5">'
    )


def test_relative_link_keeps_its_path_and_loses_its_token() -> None:
    assert redact_text('<a href="/account?session_id=abcd&amp;tab=2">Account</a>') == (
        '<a href="/account?session_id=[redacted]&amp;tab=2">Account</a>'
    )


def test_escaped_quotes_inside_json_text_stay_valid_json() -> None:
    evidence = json.dumps({"html": '<input value="jane@example.com">', "rule": "label"})
    redacted = json.loads(redact_field(evidence))
    assert redacted == {"html": '<input value="[redacted]">', "rule": "label"}


def test_query_shaped_words_in_prose_are_not_treated_as_attributes() -> None:
    text = "See https://example.com/?value=public for details"
    assert redact_text(text) == text


# --- Identifiers in text ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Signed in as jane.doe+bank@example.co.uk", f"Signed in as {REDACTED_EMAIL}"),
        ("Call 555-123-4567.", f"Call {REDACTED_PHONE}."),
        ("Call (734) 555-0199 today", f"Call {REDACTED_PHONE} today"),
        ("SSN 123-45-6789", f"SSN {REDACTED_ID_NUMBER}"),
        ("Card 4111 1111 1111 1111 on file", f"Card {REDACTED_CARD} on file"),
        (
            "Order 123e4567-e89b-12d3-a456-426614174000",
            f"Order {REDACTED_ID}",
        ),
        ("key aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z", f"key {REDACTED}"),
    ],
)
def test_identifiers_are_replaced_with_a_named_marker(text: str, expected: str) -> None:
    assert redact_text(text) == expected


def test_bearer_token_and_header_values_are_redacted() -> None:
    jwt = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    )
    assert jwt not in redact_text(f"Authorization: Bearer {jwt}")
    # A token that is not a JWT goes too, not only the word "Bearer".
    assert "abcdefghijklmnop" not in redact_text("Authorization: Bearer abcdefghijklmnop")
    assert redact_text(f"token {jwt}") == f"token {REDACTED}"
    assert redact_text("password=hunter2") == f"password={REDACTED}"


@pytest.mark.parametrize(
    "text",
    [
        # What a developer needs to find and fix the problem.
        "WCAG 1.4.3 Contrast (Minimum), Level AA",
        "main > form#login .field:nth-child(2) input",
        "2026-11-06T17:01:11",
        "Priority 0.9312345678901234",
        "/news/2026-annual-report-for-the-university-board-meeting",
        # Axcess's own evidence hash, needed to find a screenshot.
        "3f786850e387550fdab836ed7e6dc881de23001b3f786850e387550fdab836ed",
        "Card-like but invalid 4111 1111 1111 1112",
        "color-contrast",
    ],
)
def test_what_a_fix_needs_is_kept(text: str) -> None:
    assert redact_text(text) == text


def test_redaction_is_idempotent() -> None:
    text = (
        '<input value="x"> jane@example.com https://u:p@ex.com/a/123e4567-e89b-12d3-a456-'
        "426614174000?token=z#access_token=y 555-123-4567"
    )
    once = redact_text(text)
    assert redact_text(once) == once


# --- Links -------------------------------------------------------------------


def test_url_keeps_host_and_path_and_drops_secrets() -> None:
    url = (
        "https://user:pw@example.com/orders/123e4567-e89b-12d3-a456-426614174000/edit"
        "?ref=home&token=XYZ&email=jane%40example.com#access_token=abc"
    )
    assert redact_url(url) == (
        "https://[redacted]@example.com/orders/[redacted ID]/edit"
        "?ref=home&token=[redacted]&email=[redacted]#access_token=[redacted]"
    )


def test_harmless_url_keeps_its_exact_encoding() -> None:
    url = "https://example.com/search?q=a%20b&page=2#results"
    assert redact_url(url) == url


def test_markdown_link_keeps_its_closing_bracket() -> None:
    assert redact_text("[page](https://example.com/p?token=abc)") == (
        "[page](https://example.com/p?token=[redacted])"
    )


# --- Formats -------------------------------------------------------------------


def test_csv_redacts_cells_adds_a_column_and_stays_valid() -> None:
    source = io.StringIO()
    writer = csv.writer(source, lineterminator="\n")
    writer.writerow(["rule_id", "target_selector", "html", "page_url"])
    writer.writerow(
        [
            "label",
            "#email",
            '<input id="email" value="jane@example.com">',
            "https://example.com/account?session=abc",
        ]
    )

    redacted = redact_export(source.getvalue(), export_format="csv")

    assert isinstance(redacted, str)
    rows = list(csv.reader(io.StringIO(redacted)))
    assert rows[0] == ["rule_id", "target_selector", "html", "page_url", REDACTION_CSV_COLUMN]
    assert rows[1][:4] == [
        "label",
        "#email",
        '<input id="email" value="[redacted]">',
        "https://example.com/account?session=[redacted]",
    ]
    assert rows[1][4] == "Redacted (best effort)"


def test_json_redacts_strings_keeps_numbers_and_adds_the_notice() -> None:
    rendered = json.dumps(
        {"scan": {"id": 7}, "a11y_findings": [{"html_snippet": '<input value="secret">'}]}
    )

    payload = json.loads(redact_export(rendered, export_format="json"))

    assert payload["scan"] == {"id": 7}
    assert payload["a11y_findings"][0]["html_snippet"] == '<input value="[redacted]">'
    notice = payload["redaction_notice"]
    assert notice["redacted"] is True
    assert notice["best_effort"] is True
    assert notice["warning"] == REDACTION_NOTICE


@pytest.mark.parametrize("fmt", ["audit", "markdown"])
def test_markdown_starts_with_the_notice(fmt: str) -> None:
    redacted = redact_export("# Report\n\nContact jane@example.com\n", export_format=fmt)

    assert isinstance(redacted, str)
    assert redacted.startswith(f"> **{REDACTION_TITLE}**")
    assert "best effort" in redacted.split("\n\n", 1)[0]
    assert f"Contact {REDACTED_EMAIL}" in redacted
    assert "jane@example.com" not in redacted


def test_notice_states_every_limit() -> None:
    # Never shortened away (AGENTS.md, Interface language rule 4).
    for fact in (
        "best effort",
        "names and other private text",
        "text inside images",
        # A kept locator can quote a private value, so the file says so.
        "Element locators (CSS selectors) are kept whole",
        "even when one quotes a value from the page",
        "Screenshots are left out",
        "not redacted",
        "Check the file before you share it",
    ):
        assert fact in REDACTION_NOTICE


def test_workbook_cells_and_links_are_redacted_and_a_notice_sheet_added() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Issues"
    sheet["A1"] = "Element code"
    sheet["A2"] = '<input value="jane@example.com">'
    sheet["B2"] = "https://example.com/p?token=abc"
    sheet["B2"].hyperlink = "https://example.com/p?token=abc"
    sheet["C2"] = 42
    buffer = io.BytesIO()
    workbook.save(buffer)

    redacted = redact_export(buffer.getvalue(), export_format="xlsx")

    assert isinstance(redacted, bytes)
    result = load_workbook(io.BytesIO(redacted))
    assert result.sheetnames == ["REDACTION NOTICE", "Issues"]
    assert result["REDACTION NOTICE"]["B3"].value == REDACTION_NOTICE
    issues_sheet = result["Issues"]
    assert issues_sheet["A2"].value == '<input value="[redacted]">'
    assert issues_sheet["B2"].value == "https://example.com/p?token=[redacted]"
    assert issues_sheet["B2"].hyperlink.target == "https://example.com/p?token=[redacted]"
    assert issues_sheet["C2"].value == 42


def test_an_unknown_format_is_refused_rather_than_served_unredacted() -> None:
    with pytest.raises(ValueError, match="not available"):
        redact_export("x", export_format="pdf")


def test_wrong_payload_type_is_refused() -> None:
    with pytest.raises(TypeError):
        redact_export("not bytes", export_format="xlsx")
    with pytest.raises(TypeError):
        redact_export(b"bytes", export_format="csv")


# --- PR #58 review: element code ----------------------------------------------


def test_value_cut_short_with_an_apostrophe_in_it_is_redacted() -> None:
    # The quote never closes, and the value holds the other kind of quote.
    assert redact_text("<input value=\"Jane's private note") == f'<input value="{REDACTED}'
    assert redact_text('<input value=\'say "hi" to Jane') == f"<input value='{REDACTED}"


def test_greater_than_sign_in_a_quoted_attribute_does_not_end_the_tag() -> None:
    html = '<input title="a > b" value="private-note">'
    assert redact_text(html) == f'<input title="a > b" value="{REDACTED}">'
    cut_short = "<input title='a > b' value=\"private-note"
    assert redact_text(cut_short) == f"<input title='a > b' value=\"{REDACTED}"


def test_secret_after_an_html_entity_in_a_link_is_redacted() -> None:
    html = '<a href="/account?tab=2&amp;session_id=abcd">Account</a>'
    assert redact_text(html) == (f'<a href="/account?tab=2&amp;session_id={REDACTED}">Account</a>')
    # Numeric references are the same "&".
    assert "abcd" not in redact_text('<a href="/account?tab=2&#38;session_id=abcd">')
    # The same link as plain text, copied out of element code.
    assert redact_text("https://example.com/a?tab=2&amp;session_id=abcd") == (
        f"https://example.com/a?tab=2&amp;session_id={REDACTED}"
    )


def test_harmless_link_with_entities_keeps_its_exact_characters() -> None:
    html = '<a href="/search?q=chairs&amp;page=2&#38;sort=price">Next</a>'
    assert redact_text(html) == html


def test_locator_shaped_label_loses_a_form_value() -> None:
    # How a structured target is shown. A real locator is held back first
    # (see the locator tests below); this is the evidence that is left.
    assert redact_text('[value="private_suffix"]') == f'[value="{REDACTED}"]'
    assert redact_text('a[href="/x?token=abc123"]') == f'a[href="/x?token={REDACTED}"]'
    assert redact_text('input[name="q"][type="text"]') == 'input[name="q"][type="text"]'
    assert redact_text('//input[@value="private_suffix"]') == f'//input[@value="{REDACTED}"]'


# --- PR #58 review: text boxes over several lines ---------------------------------


def _markdown_body(redacted: str | bytes) -> str:
    assert isinstance(redacted, str)
    return redacted.split("\n\n", 1)[1]


def test_text_box_over_several_lines_of_a_fenced_block_is_redacted() -> None:
    report = '# Report\n\n```html\n<textarea id="notes">\nMy bank note\n</textarea>\n```\n\nAfter.'
    body = _markdown_body(redact_export(report, export_format="markdown"))
    assert "My bank note" not in body
    assert body == f'# Report\n\n```html\n<textarea id="notes">{REDACTED}</textarea>\n```\n\nAfter.'


def test_text_box_cut_short_in_a_fence_does_not_take_the_text_after_it() -> None:
    report = (
        '```\n<textarea id="notes">\nMy bank note\n```\n\n## Next issue type\n\nKeep this line.'
    )
    body = _markdown_body(redact_export(report, export_format="markdown"))
    assert "My bank note" not in body
    assert body.endswith("```\n\n## Next issue type\n\nKeep this line.")


def test_text_box_over_several_lines_outside_a_fence_stops_at_a_blank_line() -> None:
    report = "Found:\n<textarea>\nMy bank note\n\n## Next issue type\n\nKeep this line."
    body = _markdown_body(redact_export(report, export_format="markdown"))
    assert "My bank note" not in body
    assert body.endswith("\n\n## Next issue type\n\nKeep this line.")


def test_fenced_element_code_in_a_cell_does_not_take_the_text_after_it() -> None:
    # The Jira file writes element code in a fence inside one cell.
    cell = "**Failing HTML:**\n```\n<textarea>My bank note\n```\n**Rule docs:** https://example.com/rule"
    redacted = redact_field(cell)
    assert "My bank note" not in redacted
    assert redacted.endswith("```\n**Rule docs:** https://example.com/rule")


# --- PR #58 review: spreadsheet formulas ----------------------------------------


def test_text_inside_a_formula_is_redacted_and_the_formula_kept() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"] = '="jane@example.com"'
    sheet["A2"] = (
        '=HYPERLINK("https://example.com/p?token=abc", '
        '"jane@example.com said ""call 555-123-4567""")'
    )
    sheet["A3"] = "=SUM(B1:B9)"
    buffer = io.BytesIO()
    workbook.save(buffer)

    redacted = redact_export(buffer.getvalue(), export_format="xlsx")

    assert isinstance(redacted, bytes)
    result = load_workbook(io.BytesIO(redacted))[workbook.sheetnames[0]]
    assert result["A1"].value == f'="{REDACTED_EMAIL}"'
    assert result["A2"].value == (
        f'=HYPERLINK("https://example.com/p?token={REDACTED}", '
        f'"{REDACTED_EMAIL} said ""call {REDACTED_PHONE}""")'
    )
    assert result["A3"].value == "=SUM(B1:B9)"


# --- PR #58 review: element locators are kept whole --------------------------------

_LOCATOR = 'input[data-user="jane@example.com"]'
_ELEMENT = '<input data-user="jane@example.com" value="jane@example.com">'


def test_without_a_known_locator_the_same_text_is_redacted() -> None:
    # The fix brief works this way on purpose, and says a locator is not exact.
    assert "jane@example.com" not in redact_text(_LOCATOR)


def test_json_keeps_a_recorded_locator_and_redacts_the_value_elsewhere() -> None:
    rendered = json.dumps(
        {
            "a11y_findings": [
                {
                    "target_selector": _LOCATOR,
                    "target_display": _LOCATOR,
                    "html_snippet": _ELEMENT,
                    "failure_summary": "No label for jane@example.com",
                }
            ]
        }
    )
    redacted = redact_export(rendered, export_format="json", locators=[_LOCATOR])
    assert isinstance(redacted, str)
    finding = json.loads(redacted)["a11y_findings"][0]
    assert finding["target_selector"] == _LOCATOR
    assert finding["target_display"] == _LOCATOR
    assert finding["html_snippet"] == f'<input data-user="{REDACTED_EMAIL}" value="{REDACTED}">'
    assert finding["failure_summary"] == f"No label for {REDACTED_EMAIL}"


def test_csv_and_jira_keep_a_recorded_locator_inside_a_cell() -> None:
    source = io.StringIO(newline="")
    writer = csv.writer(source)
    writer.writerow(["target_selector", "html_snippet", "Description"])
    writer.writerow(
        [_LOCATOR, _ELEMENT, f"**Target selector:** `{_LOCATOR}`\nOwner jane@example.com"]
    )
    for fmt in ("csv", "jira"):
        redacted = redact_export(source.getvalue(), export_format=fmt, locators=[_LOCATOR])
        assert isinstance(redacted, str)
        row = list(csv.reader(io.StringIO(redacted)))[1]
        assert row[0] == _LOCATOR
        assert row[1] == f'<input data-user="{REDACTED_EMAIL}" value="{REDACTED}">'
        assert row[2] == f"**Target selector:** `{_LOCATOR}`\nOwner {REDACTED_EMAIL}"


@pytest.mark.parametrize("fmt", ["audit", "markdown"])
def test_markdown_keeps_a_recorded_locator(fmt: str) -> None:
    report = f"- **Technical target:** `{_LOCATOR}`. Owner jane@example.com"
    body = _markdown_body(redact_export(report, export_format=fmt, locators=[_LOCATOR]))
    assert body == f"- **Technical target:** `{_LOCATOR}`. Owner {REDACTED_EMAIL}"


def test_workbook_keeps_a_recorded_locator_in_a_cell_of_several() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"] = f"#main\n{_LOCATOR}"
    sheet["B1"] = _ELEMENT
    buffer = io.BytesIO()
    workbook.save(buffer)

    redacted = redact_export(buffer.getvalue(), export_format="xlsx", locators=[_LOCATOR])

    assert isinstance(redacted, bytes)
    result = load_workbook(io.BytesIO(redacted))[workbook.sheetnames[0]]
    assert result["A1"].value == f"#main\n{_LOCATOR}"
    assert "jane@example.com" not in result["B1"].value


@pytest.mark.parametrize(
    "locator",
    [
        # One for each kind of thing the redactor replaces. The redactor
        # takes a quick first look at each locator before running every pass
        # on it; this fails if that first look misses a kind.
        "#jane.doe+bank@example.co.uk",
        "#tel 555-123-4567",
        "#tel (734) 555-0199",
        "#ssn 123-45-6789",
        "#card 4111 1111 1111 1111",
        "#card4111111111111111",
        "#order 123e4567-e89b-12d3-a456-426614174000",
        "#key aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z",
        "#jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abc",
        "#auth Bearer abcdefghijklmnop",
        "#x-api-key: abc",
        "#cookie: abc",
        "#password=hunter2",
        'a[href="https://example.com/reset?token=abc123"]',
        'input[value="private note"]',
        "//input[@value='private note']",
    ],
)
def test_a_locator_quoting_any_kind_of_private_value_is_kept(locator: str) -> None:
    # The premise: with no locator given, each of these would be changed.
    assert redact_text(locator) != locator
    rendered = json.dumps({"target_selector": locator, "note": f"at {locator} today"})
    redacted = redact_export(rendered, export_format="json", locators=[locator])
    assert isinstance(redacted, str)
    assert json.loads(redacted)["target_selector"] == locator
    assert json.loads(redacted)["note"] == f"at {locator} today"


def test_scan_locators_are_text_targets_not_structured_evidence() -> None:
    class Finding:
        def __init__(self, target_selector: str) -> None:
            self.target_selector = target_selector

    structured = json.dumps({"type": "attribute", "name": "value", "value": "private_suffix"})
    assert scan_locators(
        [Finding(_LOCATOR), Finding('[data-user="x"]'), Finding(structured), Finding("")]
    ) == frozenset({_LOCATOR, '[data-user="x"]'})


# --- PR #58 review: structured evidence (JSON) -------------------------------------


def test_structured_attribute_value_is_redacted_by_the_attribute_name() -> None:
    evidence = {
        "target": {"type": "attribute", "name": "value", "value": "private_suffix"},
        "element": {
            "type": "element",
            "name": "input",
            "attributes": [
                {"name": "id", "value": "card"},
                {"name": "value", "value": "private_suffix"},
                {"name": "formaction", "value": "/pay?token=abc123"},
            ],
        },
    }
    redacted = json.loads(redact_field(json.dumps(evidence)))
    assert redacted["target"] == {"type": "attribute", "name": "value", "value": REDACTED}
    assert redacted["element"]["attributes"] == [
        {"name": "id", "value": "card"},
        {"name": "value", "value": REDACTED},
        {"name": "formaction", "value": f"/pay?token={REDACTED}"},
    ]


def test_structured_text_box_text_and_secret_named_fields_are_redacted() -> None:
    evidence = {
        "element": {
            "type": "element",
            "name": "textarea",
            "children": [{"type": "text", "data": "My loan was declined"}],
        },
        "csrf_token": "abc",
        "rule": "sia-r8",
    }
    redacted = json.loads(redact_field(json.dumps(evidence)))
    assert redacted["element"]["children"] == [{"type": "text", "data": REDACTED}]
    assert redacted["csrf_token"] == REDACTED
    assert redacted["rule"] == "sia-r8"


def test_evidence_json_embedded_in_the_json_export_is_redacted() -> None:
    evidence = json.dumps(
        {"target": {"type": "attribute", "name": "value", "value": "private_suffix"}}
    )
    rendered = json.dumps({"a11y_findings": [{"engine_evidence_json": evidence}]})
    redacted = redact_export(rendered, export_format="json")
    assert isinstance(redacted, str)
    assert "private_suffix" not in redacted
    embedded = json.loads(json.loads(redacted)["a11y_findings"][0]["engine_evidence_json"])
    assert embedded["target"]["value"] == REDACTED


def test_evidence_json_cut_short_is_still_redacted() -> None:
    # It no longer parses, so the structure is read from the text.
    cut = '{"target":{"type":"attribute","name":"value","value":"private_suf'
    assert (
        redact_field(cut) == f'{{"target":{{"type":"attribute","name":"value","value":"{REDACTED}'
    )
    quoted = 'Target {"name": "value", "value": "a \\"private\\" note"} was checked'
    assert redact_text(quoted) == f'Target {{"name": "value", "value": "{REDACTED}"}} was checked'


# --- PR #58 review: evidence redacted before a sentence is made from it -------------


def test_redact_evidence_returns_a_redacted_copy_and_keeps_the_locator() -> None:
    structured = json.dumps({"type": "attribute", "name": "value", "value": "private_suffix"})
    stored = {
        "target_selector": _LOCATOR,
        "html_snippet": "<textarea>My loan was declined</textarea>",
        "engine_evidence_json": json.dumps({"target": json.loads(structured)}),
        "failure_summary": "left for the pass over the finished file",
    }
    before = dict(stored)

    copy = redact_evidence(stored)

    assert stored == before
    assert copy["target_selector"] == _LOCATOR
    assert copy["html_snippet"] == f"<textarea>{REDACTED}</textarea>"
    assert "private_suffix" not in copy["engine_evidence_json"]
    assert copy["failure_summary"] == stored["failure_summary"]
    # A structured target is evidence, not a locator.
    assert (
        "private_suffix" not in redact_evidence({"target_selector": structured})["target_selector"]
    )
