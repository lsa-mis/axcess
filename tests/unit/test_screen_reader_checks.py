"""The shared screen reader steps load, read plainly, and reach every issue that uses them."""

from __future__ import annotations

import re
from importlib import resources

import pytest

from audit.web import issues, screen_reader_checks

LANDMARK_RULES = {
    "region",
    "landmark-one-main",
    "landmark-banner-is-top-level",
    "landmark-complementary-is-top-level",
    "landmark-contentinfo-is-top-level",
    "landmark-main-is-top-level",
    "landmark-no-duplicate-banner",
    "landmark-no-duplicate-contentinfo",
    "landmark-no-duplicate-main",
    "landmark-unique",
}

# Every card that names a shared check, by (section, key).
EXPECTED = {
    **{("axe_rules", rule): "landmarks" for rule in LANDMARK_RULES},
    ("axe_rules", "page-has-heading-one"): "headings",
    ("axe_rules", "heading-order"): "headings",
    ("semantic_criteria", "2.4.6"): "headings",
    ("alfa_rules", "sia-r64"): "headings",
    ("axe_rules", "link-name"): "links",
    ("axe_rules", "identical-links-same-purpose"): "links",
    ("semantic_criteria", "2.4.4"): "links",
    ("alfa_rules", "sia-r11"): "links",
    ("alfa_rules", "sia-r41"): "links",
}
CHECKS = ("landmarks", "headings", "links")


def test_landmark_check_has_mac_and_windows_steps() -> None:
    check = screen_reader_checks.check_for("landmarks")
    assert check is not None
    assert [p.id for p in check.platforms] == ["mac", "windows"]
    mac, windows = check.platforms
    assert "{Command} + {F5}" in mac.steps[0]
    assert "{Control} + {Option} + {U}" in mac.steps[1]
    assert "{Right Arrow}" in mac.steps[2]
    assert "{NVDA key} + {F7}" in windows.steps[1]
    assert windows.link_url == "https://www.nvaccess.org/download/"


@pytest.mark.parametrize(
    ("key", "rotor_item", "nvda_alt"),
    [("landmarks", "Landmarks", "D"), ("headings", "Headings", "H"), ("links", "Links", "K")],
)
def test_each_check_opens_its_own_list(key: str, rotor_item: str, nvda_alt: str) -> None:
    check = screen_reader_checks.check_for(key)
    assert check is not None
    mac, windows = check.platforms
    assert f'until you hear "{rotor_item}"' in mac.steps[2]
    assert f"Choose {rotor_item}: press {{Alt}} + {{{nvda_alt}}}." == windows.steps[2]


def test_checks_share_the_same_on_and_off_steps() -> None:
    """A reader learns turning the screen reader on and off once (COGA)."""
    checks = [screen_reader_checks.check_for(key) for key in CHECKS]
    first = checks[0]
    assert first is not None
    for check in checks[1:]:
        assert check is not None
        for mine, theirs in zip(check.platforms, first.platforms, strict=True):
            assert (mine.id, mine.name, mine.intro, mine.link_url) == (
                theirs.id,
                theirs.name,
                theirs.intro,
                theirs.link_url,
            )
            assert mine.steps[:2] == theirs.steps[:2]
            assert mine.steps[-1] == theirs.steps[-1]


@pytest.mark.parametrize("key", CHECKS)
def test_steps_spell_keys_out_and_use_no_html(key: str) -> None:
    check = screen_reader_checks.check_for(key)
    assert check is not None
    for platform in check.platforms:
        for text in [platform.intro or "", *platform.steps]:
            # WCAG 3.1.4: no "VO+U" or "NVDA+F7" shorthand.
            assert not re.search(r"\bVO\b|NVDA\+", text), text
            assert "<" not in text and ">" not in text, text
            # Every brace opens and closes a key.
            assert text.count("{") == text.count("}"), text


def test_plain_text_drops_key_braces() -> None:
    assert screen_reader_checks.plain_text("press {Command} + {F5}.") == "press Command + F5."
    check = screen_reader_checks.check_for("landmarks")
    assert check is not None
    lines = screen_reader_checks.as_text_lines(check)
    assert lines[0] == "Mac, with VoiceOver:"
    assert "Windows, with NVDA:" in lines
    assert not any("{" in line for line in lines)


def test_unknown_or_missing_check_is_none() -> None:
    assert screen_reader_checks.check_for(None) is None
    assert screen_reader_checks.check_for("") is None
    assert screen_reader_checks.check_for("no-such-check") is None


def test_every_card_that_needs_steps_uses_the_shared_ones() -> None:
    rules = issues._load_rules()
    named = {
        (section, str(key)): card["screen_reader_check"]
        for section, cards in rules.items()
        if isinstance(cards, dict)
        for key, card in cards.items()
        if isinstance(card, dict) and card.get("screen_reader_check")
    }
    assert named == EXPECTED
    for (section, key), check in EXPECTED.items():
        assert screen_reader_checks.check_for(check) is not None, check
        text = rules[section][key]["verify_manual"]
        # The card says what to find and points to the steps; the keys
        # themselves live only in the shared steps, so they cannot drift.
        assert "steps for Mac and Windows are below" in text, key
        assert "VO+" not in text and "Insert+F7" not in text, key


def test_no_card_uses_the_vo_shorthand() -> None:
    """WCAG 3.1.4: "VO" is never written out as a key name."""
    text = (resources.files("audit.rules") / "audit_report.yaml").read_text(encoding="utf-8")
    assert "VO+" not in text


def test_markdown_report_prints_the_steps_under_the_manual_check() -> None:
    from audit.exports.audit_report import AuditCard, _render_card

    check = screen_reader_checks.check_for("landmarks")
    card = AuditCard(
        pipeline="axe",
        title="Some page content is outside a landmark",
        wcag_sc="1.3.1",
        wcag_name="Info and Relationships",
        wcag_level="A",
        severity="Moderate",
        severity_reason="",
        effort="Intermediate",
        owner="Developer",
        abilities=("vision",),
        affected_page_count=1,
        affected_finding_count=1,
        triaged_count=0,
        locations=[],
        location_overflow=0,
        what_happening="x",
        why_matters="y",
        fix_steps=["z"],
        verify_manual="Open the list of landmarks (steps for Mac and Windows are below).",
        verify_automated=None,
        acceptance=None,
        confidence="High",
        needs_human_review=False,
        note=None,
        finding_ids=[],
        screen_reader_check=check,
    )
    text = "\n".join(_render_card(1, card))
    manual = text.index("- **Manual:**")
    mac = text.index("  - **Mac, with VoiceOver:** VoiceOver is built into every Mac.")
    assert manual < mac
    assert "    1. Turn VoiceOver on: press Command + F5." in text
    assert "    [Get NVDA from NV Access](https://www.nvaccess.org/download/)" in text
    assert "{" not in text[manual:]
