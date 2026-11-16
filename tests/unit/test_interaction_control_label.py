"""What "After clicking ..." says for the control Click-Through operated."""

from __future__ import annotations

from audit.analyzer.interaction.probe import _control_label


def test_a_named_control_reads_as_its_name() -> None:
    assert _control_label({"label": "Menu", "tag": "button", "shape": "button.toggle"}) == "Menu"


def test_an_unnamed_control_says_which_one_it_is() -> None:
    # It used to read "<button>", the same for every unnamed button on a page.
    control = {"label": "", "tag": "button", "shape": "button.menu-toggle.icon"}
    assert _control_label(control) == "button with no name (button.menu-toggle.icon)"
    assert _control_label({"label": "", "tag": "a", "shape": "a#open-map"}) == (
        "link with no name (a#open-map)"
    )
    assert _control_label({"label": "", "tag": "div", "shape": "div.card"}) == (
        "element with no name (div.card)"
    )


def test_an_unnamed_control_with_no_id_or_class_keeps_its_tag() -> None:
    assert _control_label({"label": "", "tag": "button", "shape": "button."}) == (
        "button with no name (<button>)"
    )
