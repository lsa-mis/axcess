"""Every issue a scan can report has written guidance, and every card is fit to show.

The Issue guidance dialog shows a card's words to people, so each card must
be complete, use only the markup its field is rendered with, and follow
docs/plain-language.md. Which cards must exist is read from the checks
themselves: the bundled axe-core, the installed Alfa rules (when the runner
is installed), the AI review's analyzers, and the image text check's groups.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
import yaml

import audit
from audit.analyzer.axe import _extract_wcag_scs, tags_for_level
from audit.synthesizer.alt_compare import AltAdequacy
from audit.web.image_findings_queries import _CLASSIFICATION_LABELS

SRC = Path(audit.__file__).resolve().parent
AXE_BUNDLE = SRC / "web/static/axe.min.js"
ALFA_RULES = SRC / "alfa_runner/node_modules/@siteimprove/alfa-rules/dist"

REQUIRED = (
    "what_happening",
    "why_matters",
    "owner",
    "effort",
    "fix_steps",
    "verify_manual",
    "verify_automated",
    "acceptance",
    "confidence_default",
    "abilities_affected",
)
# Shown as text: an element name such as <li> reads as written, but <code>
# and entities would show as typed.
PLAIN = ("title", "wcag_name", "why_matters", "verify_manual", "verify_automated", "acceptance")
# Nouns docs/plain-language.md says not to use (the verb "finding" is fine).
BANNED = (
    r"remediat",
    r"\bfindings\b",
    r"\b(?:a|the|this|that|each|every|one) finding\b",
    r"(?<!for )\binstances?\b",
    r"\bdeterministic\b",
    r"canttell",
    r"\bviolations?\b",
    r"\bsnippets?\b",
    r"outerhtml",
    r"success criteri",
    r"\bpipelines?\b",
    r"\bprobes?\b",
    r"likely barrier",
    r"review lead",
)


def _cards() -> dict[str, Any]:
    text = (resources.files("audit.rules") / "audit_report.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _axe_rules_a_scan_runs() -> dict[str, list[str]]:
    """Rule id -> tags for every axe rule a scan's tags select."""
    scan_tags = {
        tag
        for version in ("2.1", "2.2")
        for level in ("A", "AA", "AAA")
        for tag in tags_for_level(level, version)  # type: ignore[arg-type]
    }
    bundle = AXE_BUNDLE.read_text(encoding="utf-8")
    rules = {}
    for rule_id, raw_tags in re.findall(r'id:"([a-z0-9-]+)"[^{}]{0,400}?tags:\[([^\]]*)\]', bundle):
        tags = re.findall(r'"([^"]+)"', raw_tags)
        if set(tags) & scan_tags and not {"experimental", "deprecated"} & set(tags):
            rules[rule_id] = tags
    return rules


# axe tags these best practice only, yet Axcess files them under a WCAG
# criterion (Focus Order; Info and Relationships). Whether to keep that is an
# open product decision: moving them changes how the issues are counted.
FILED_UNDER_WCAG_BY_AXCESS = {"tabindex": "2.4.3", "heading-order": "1.3.1"}


def test_every_axe_rule_a_scan_runs_has_a_card() -> None:
    rules = _axe_rules_a_scan_runs()
    assert len(rules) > 80, "the axe bundle was not read"
    cards = _cards()["axe_rules"]
    assert sorted(set(rules) - set(cards)) == []
    for rule_id, tags in rules.items():
        primary, _all, level = _extract_wcag_scs(tags)
        card = cards[rule_id]
        if primary:
            # A card never re-files an issue under another criterion.
            assert card.get("wcag_sc") in (None, primary), rule_id
            assert card.get("wcag_level") in (None, level), rule_id
        elif rule_id in FILED_UNDER_WCAG_BY_AXCESS:
            assert card.get("wcag_sc") == FILED_UNDER_WCAG_BY_AXCESS[rule_id], rule_id
        else:
            assert "wcag_sc" not in card and "wcag_level" not in card, rule_id


def test_every_alfa_rule_the_runner_selects_has_a_card() -> None:
    if not (ALFA_RULES / "rules.js").exists():
        pytest.skip("the Alfa runner is not installed")
    listed = re.findall(r'from "\./(sia-r\d+)/rule\.js"', (ALFA_RULES / "rules.js").read_text())
    # The runner runs the rules tied to a WCAG criterion at the scan's level.
    selectable = [
        rule_id
        for rule_id in listed
        if 'Criterion.of("' in (ALFA_RULES / rule_id / "rule.js").read_text()
    ]
    assert len(selectable) > 40
    cards = _cards()["alfa_rules"]
    assert sorted(set(selectable) - set(cards)) == []


def test_every_ai_review_criterion_has_a_card() -> None:
    analyzers = SRC / "analyzer/semantic/analyzers"
    criteria = [
        ".".join(match.groups())
        for path in analyzers.glob("sc_*.py")
        if (match := re.fullmatch(r"sc_(\d+)_(\d+)_(\d+)\.py", path.name))
    ]
    assert criteria
    assert sorted(set(criteria) - set(_cards()["semantic_criteria"])) == []


def test_every_image_group_has_a_card() -> None:
    groups = {
        f"{classification or 'unclassified'}_{adequacy.value}"
        for classification in _CLASSIFICATION_LABELS
        for adequacy in AltAdequacy
    }
    assert sorted(groups - set(_cards()["image_findings"])) == []


def _all_cards() -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (section, str(key), card)
        for section, entries in _cards().items()
        if isinstance(entries, dict)
        for key, card in entries.items()
    ]


def _texts(card: dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for field, value in card.items():
        if isinstance(value, str):
            out.append((field, value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    out.append((field, item))
                elif isinstance(item, dict):
                    out.extend((f"{field}.{k}", v) for k, v in item.items() if isinstance(v, str))
    return out


@pytest.mark.parametrize(("section", "key", "card"), _all_cards(), ids=lambda v: str(v)[:40])
def test_every_card_is_complete_and_fit_to_show(
    section: str, key: str, card: dict[str, Any]
) -> None:
    missing = [field for field in REQUIRED if field not in card]
    assert missing == [], missing
    for field in REQUIRED:
        if field != "abilities_affected":
            assert card[field], field
    if section == "alfa_rules":
        # An Alfa issue keeps its own title and criterion.
        assert not {"title", "wcag_sc", "wcag_name", "wcag_level"} & set(card)
    else:
        assert card.get("title")
    assert card["owner"] in {"dev", "editor", "designer", "content"}
    assert card["effort"] in {"under_15m", "under_2h", "multi_sprint"}
    assert card["confidence_default"] in {"high", "medium", "low"}
    assert set(card["abilities_affected"]) <= {"vision", "cognition", "motor", "hearing"}
    for option in card.get("fix_options") or []:
        assert option.get("label") and option.get("approach"), option
    for field, text in _texts(card):
        inner = " ".join(re.findall(r"<code>([\s\S]*?)</code>", text))
        # Code inside <code> is escaped, so it is shown, never run.
        assert "<" not in inner and ">" not in inner, (field, text)
        if field in PLAIN:
            assert "<code>" not in text and not re.search(r"&(lt|gt|amp|quot);", text), (
                field,
                text,
            )
        if field == "fix_steps":
            # Rendered as HTML: <code> is the only element allowed.
            tags = set(re.findall(r"<[^>]*>", text)) - {"<code>", "</code>"}
            assert tags == set(), (field, tags)
        prose = re.sub(r"<code>[\s\S]*?</code>", "", text)
        for pattern in BANNED:
            assert not re.search(pattern, prose, re.I), (field, pattern, text)
