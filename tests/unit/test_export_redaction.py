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
    redact_export,
    redact_field,
    redact_text,
    redact_url,
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
