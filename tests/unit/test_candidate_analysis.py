"""Candidate discovery must not silently become a claim about keyboard behavior."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.tabbing.runner import candidate_analysis as ca


def feature(**changes):
    return {
        "visible": True,
        "inert": False,
        "pointer_events_none": False,
        "center_hit": True,
        "native": False,
        "has_key_handler": False,
        "closed_shadow": False,
        "delegated_types": [],
        "label_toggle": False,
        "control_probe": None,
        "control_disabled": None,
        **changes,
    }


def proposals(**changes):
    return {"D4": set(), "D5": set(), "D6": set(), "D8": set(), **changes}


def test_focusable_mouse_controls_stay_candidates_even_when_they_have_a_key_handler():
    result = ca.build_variants(
        proposals(D5={"missing-key", "different-effect", "native"}),
        {
            "missing-key": feature(),
            "different-effect": feature(has_key_handler=True),
            "native": feature(native=True),
        },
        {"missing-key", "different-effect", "native"},
    )
    assert result.reported[ca.UNION] == set()
    assert result.reported[ca.FOCUSABLE] == {"missing-key"}
    assert result.proposed[ca.FOCUSABLE] == {"missing-key", "different-effect"}
    assert "different-effect" in result.proposed[ca.HYBRID]
    assert "different-effect" not in result.reported[ca.HYBRID]


def test_visible_label_is_kept_when_its_toggle_is_hidden():
    result = ca.build_variants(
        proposals(),
        {
            "bad-label": feature(label_toggle=True, control_probe="hidden", control_disabled=False),
            "hidden": feature(visible=False, native=True),
            "good-label": feature(
                label_toggle=True, control_probe="clipped", control_disabled=False
            ),
            "clipped": feature(native=True),
        },
        {"clipped"},
    )
    assert result.proposed[ca.LABEL] == {"bad-label", "good-label"}
    assert result.reported[ca.LABEL] == {"bad-label"}
    assert result.exclusions["bad-label"] == []
    assert result.exclusions["hidden"] == ["upstream visibility test failed"]


def test_unlabelled_or_unfinished_control_reachability_is_not_a_known_failure():
    result = ca.build_variants(
        proposals(),
        {"label": feature(label_toggle=True, control_probe=None, control_disabled=False)},
        set(),
    )
    assert result.unknown[ca.LABEL] == {"label"}
    assert result.reported[ca.LABEL] == set()
    capped = ca.build_variants(
        proposals(),
        {"label": feature(label_toggle=True, control_probe="later", control_disabled=False)},
        set(),
        capped=True,
    )
    assert capped.unknown[ca.LABEL] == {"label"}


def test_pointer_and_center_gates_are_separate_from_the_upstream_union():
    features = {
        "clear": feature(),
        "inert": feature(inert=True),
        "pointer": feature(pointer_events_none=True),
        "covered": feature(center_hit=False),
        "offscreen": feature(center_hit=None),
    }
    result = ca.build_variants(proposals(D4=set(features)), features, set())
    assert result.reported[ca.UNION] == set(features)
    assert result.reported[ca.POINTER_GATE] == {"clear", "covered", "offscreen"}
    assert result.reported[ca.CENTER_GATE] == {"clear", "offscreen"}


def test_closed_root_missing_from_tab_is_uncertain_for_improved_rules():
    result = ca.build_variants(
        proposals(D4={"opaque"}), {"opaque": feature(closed_shadow=True)}, set()
    )
    assert result.reported[ca.UNION] == {"opaque"}
    assert result.reported[ca.POINTER_GATE] == set()
    assert result.unknown[ca.POINTER_GATE] == {"opaque"}


def test_delegation_is_a_broad_candidate_signal_with_possible_false_alarms():
    result = ca.build_variants(
        proposals(),
        {
            "action": feature(delegated_types=["click"]),
            "decorative": feature(delegated_types=["click"]),
            "button": feature(delegated_types=["click"], native=True),
        },
        {"button"},
    )
    # The feature deliberately cannot know whether the ancestor's callback
    # handles one child and ignores the other. Both leads must stay auditable.
    assert result.proposed[ca.DELEGATED] == {"action", "decorative"}
    assert result.reported[ca.DELEGATED] == {"action", "decorative"}
