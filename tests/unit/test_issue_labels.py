"""The user-facing label tables stay complete and in step with the client."""

from __future__ import annotations

import re
from pathlib import Path

from audit import labels

FRONTEND_LABELS = Path(__file__).resolve().parents[2] / "src/audit/web/frontend/src/lib/labels.ts"
TERMS = FRONTEND_LABELS.with_name("terms.ts")


def test_every_key_has_a_label_and_help() -> None:
    assert set(labels.FINDING_TYPE_LABELS) == set(labels.FINDING_TYPES)
    assert set(labels.FINDING_TYPE_HELP) == set(labels.FINDING_TYPES)
    assert set(labels.REVIEW_LANE_LABELS) == set(labels.REVIEW_LANES)
    assert set(labels.REVIEW_LANE_HELP) == set(labels.REVIEW_LANES)


def test_click_through_is_the_feature_name() -> None:
    assert labels.CLICK_THROUGH == "Click-Through"
    # The badge says when it was found; the feature keeps its name.
    assert labels.FINDING_TYPE_LABELS["click_through"] == "After clicking"
    assert labels.click_through_states(1) == "1 page state opened by clicking"
    assert labels.click_through_states(3) == "3 page states opened by clicking"
    for text in (*labels.FINDING_TYPE_HELP.values(), *labels.REVIEW_LANE_HELP.values()):
        assert "dom state" not in text.lower()


def _ts_record(name: str, path: Path | None = None) -> dict[str, str]:
    """A ``Record<Key, string>`` from labels.ts (or ``path``); values are literals or constants."""
    source = (path or FRONTEND_LABELS).read_text()
    constants = dict(re.findall(r'^export const (\w+) = "([^"]*)";', source, re.M))
    body = re.search(rf"export const {name}[^=]*= \{{(.*?)\n\}};", source, re.S)
    assert body, name
    entries = re.findall(r'^\s*(\w+):\s*(?:"([^"]*)"|(\w+)),?$', body.group(1), re.M)
    # Help text is written on the line after its key.
    wrapped = re.findall(r'^\s*(\w+):\s*\n\s*"([^"]*)",?$', body.group(1), re.M)
    out = {key: literal or constants[const] for key, literal, const in entries}
    out.update(dict(wrapped))
    return out


def test_frontend_labels_match_the_server() -> None:
    """The React table and the exports must use the same words."""
    assert _ts_record("FINDING_TYPE_LABELS") == dict(labels.FINDING_TYPE_LABELS)
    assert _ts_record("FINDING_TYPE_HELP") == dict(labels.FINDING_TYPE_HELP)
    # The frontend takes the type names from terms.ts, the one source every
    # screen reads; labels.ts re-exports them as REVIEW_LANE_LABELS.
    assert _ts_record("REVIEW_TYPE_LABEL", TERMS) == dict(labels.REVIEW_LANE_LABELS)
    assert _ts_record("REVIEW_LANE_HELP") == dict(labels.REVIEW_LANE_HELP)
