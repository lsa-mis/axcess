"""Wording-check requests sized to the model's window (2026-11-19).

SC 2.4.4 sent a 50-link page as one 10,773-token request against the
private service's 8,192-token window, and llama.cpp refused it.
"""

from __future__ import annotations

from audit.analyzer.semantic.budget import (
    ANSWER_TOKENS,
    CONTEXT_TOKENS,
    PROMPT_CHARS,
    fit_batches,
)


def _render(items: list[str]) -> str:
    return "\n".join(f"{i}: {item}" for i, item in enumerate(items))


def test_everything_that_fits_goes_in_one_batch() -> None:
    items = ["a", "b", "c"]
    assert fit_batches(items, _render, "template", prompt_chars=1000) == [items]


def test_batches_keep_order_and_each_fits() -> None:
    items = [f"item {n} " + "x" * 40 for n in range(30)]
    template = "t" * 100
    batches = fit_batches(items, _render, template, prompt_chars=600)
    assert len(batches) > 1
    assert [item for batch in batches for item in batch] == items
    for batch in batches:
        assert len(template) + len(_render(batch)) <= 600


def test_an_item_too_big_alone_still_goes_alone() -> None:
    items = ["small", "x" * 5000, "small too"]
    batches = fit_batches(items, _render, "", prompt_chars=100)
    assert batches == [["small"], ["x" * 5000], ["small too"]]


def test_no_items_no_batches() -> None:
    assert fit_batches([], _render, "t") == []


def test_the_prompt_and_answer_fit_the_window() -> None:
    # At the conservative 2.5 characters per token, a full prompt plus the
    # longest answer stays inside the window.
    assert PROMPT_CHARS / 2.5 + ANSWER_TOKENS < CONTEXT_TOKENS
