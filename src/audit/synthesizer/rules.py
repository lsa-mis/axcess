"""Load and look up remediation hints from ``rules/remediation.yaml``.

The YAML is matched in declaration order: first rule whose
``(classification, adequacy)`` pair matches wins. Use ``classification: "*"``
for fallbacks (e.g. inline SVG text where there's no VLM classification).
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import yaml

from audit.synthesizer.alt_compare import AltAdequacy

_RULES_PACKAGE = "audit.rules"
_RULES_FILE = "remediation.yaml"

_WILDCARD = "*"


@dataclass(frozen=True)
class Rule:
    classification: str
    adequacy: str
    hint: str


class RemediationRules:
    """In-memory, ordered list of rules with ``.lookup(classification, adequacy)``."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    @classmethod
    def load(cls, *, name: str = _RULES_FILE) -> RemediationRules:
        text = (resources.files(_RULES_PACKAGE) / name).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        raw_rules = data.get("rules", [])
        parsed: list[Rule] = []
        for item in raw_rules:
            parsed.append(
                Rule(
                    classification=str(item["classification"]),
                    adequacy=str(item["adequacy"]),
                    hint=" ".join(str(item["hint"]).split()),
                )
            )
        return cls(parsed)

    def lookup(self, classification: str | None, adequacy: AltAdequacy) -> str | None:
        """First-matching rule's hint, or ``None`` if nothing matched."""
        want_class = classification or _WILDCARD
        for rule in self._rules:
            if rule.adequacy != adequacy.value:
                continue
            if rule.classification in (want_class, _WILDCARD):
                return rule.hint
        return None

    def __len__(self) -> int:
        return len(self._rules)
