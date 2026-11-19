"""Wording-check requests: as few as fit, and a fixed answer shape (2026-11-19).

SC 2.4.4 sent a 50-link page as one 10,773-token request against the
private service's 8,192-token window. The first fix split by a fixed
2.5 characters per token and sent up to 6 small requests per page. Now
the prompt is counted by the model and split only when it does not fit.
"""

from __future__ import annotations

import pytest

from audit.analyzer.semantic.budget import (
    ANSWER_TOKENS,
    CONTEXT_TOKENS,
    FALLBACK_CHARS_PER_TOKEN,
    PROMPT_TOKENS,
    fit_batches,
    plan_batches,
    violations_schema,
)


def _prompt(items: list[str]) -> str:
    return "INSTRUCTIONS\n" + "\n".join(f"{i}: {item}" for i, item in enumerate(items))


def test_batches_keep_order_and_each_fits() -> None:
    items = [f"item {n} " + "x" * 40 for n in range(30)]
    batches = fit_batches(items, _prompt, prompt_chars=600)
    assert len(batches) > 1
    assert [item for batch in batches for item in batch] == items
    assert all(len(_prompt(batch)) <= 600 for batch in batches)


def test_an_item_too_big_alone_still_goes_alone() -> None:
    items = ["small", "x" * 5000, "small too"]
    assert fit_batches(items, _prompt, prompt_chars=100) == [
        ["small"],
        ["x" * 5000],
        ["small too"],
    ]


@pytest.mark.asyncio
async def test_a_prompt_that_fits_goes_in_one_request() -> None:
    items = [f"link {n}" for n in range(50)]
    counted: list[str] = []

    async def count(text: str) -> int:
        counted.append(text)
        return PROMPT_TOKENS

    assert await plan_batches(items, _prompt, count) == [items]
    assert counted == [_prompt(items)]  # one count for the whole page


@pytest.mark.asyncio
async def test_a_prompt_too_long_is_split_by_its_measured_ratio() -> None:
    items = ["y" * 1000 for _ in range(40)]
    whole = _prompt(items)

    async def count(text: str) -> int:
        # This model reads 4 characters per token.
        return len(text) // 4

    batches = await plan_batches(items, _prompt, count)
    assert len(batches) > 1
    assert [item for batch in batches for item in batch] == items
    for batch in batches:
        assert len(_prompt(batch)) // 4 <= PROMPT_TOKENS
    # Not split more than the window needs: about whole / budget requests.
    assert len(batches) <= len(whole) // 4 // int(PROMPT_TOKENS * 0.9) + 1


@pytest.mark.asyncio
async def test_without_a_count_the_estimate_is_used() -> None:
    items = ["z" * 1000 for _ in range(40)]

    async def unknown(_text: str) -> None:
        return None

    batches = await plan_batches(items, _prompt, unknown)
    limit = int(PROMPT_TOKENS * FALLBACK_CHARS_PER_TOKEN)
    assert len(batches) > 1
    assert all(len(_prompt(batch)) <= limit for batch in batches)


@pytest.mark.asyncio
async def test_no_items_no_requests() -> None:
    async def count(_text: str) -> int:
        raise AssertionError("nothing to count")

    assert await plan_batches([], _prompt, count) == []


def test_the_prompt_and_answer_fit_the_window() -> None:
    assert PROMPT_TOKENS + ANSWER_TOKENS < CONTEXT_TOKENS


def test_the_answer_schema_names_only_this_requests_items() -> None:
    schema = violations_schema(7)
    entry = schema["properties"]["violations"]["items"]
    assert schema["required"] == ["violations"]
    assert schema["properties"]["violations"]["maxItems"] == 7
    assert entry["properties"]["index"] == {"type": "integer", "minimum": 0, "maximum": 6}
    assert entry["properties"]["confidence"] == {"enum": ["high", "medium", "low"]}
    assert set(entry["required"]) == {"index", "reason", "recommendation", "confidence"}
    assert entry["properties"]["reason"]["maxLength"] <= 300
