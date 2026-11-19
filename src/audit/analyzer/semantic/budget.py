"""How much one wording-check request may carry, the answer's length and shape.

The private llama.cpp service gives each request an 8,192-token window
(``audit.ai.runtime.CONTEXT_TOKENS``), shared by the prompt and the
answer. A link-heavy page used to overflow it: SC 2.4.4 sent 50 links,
each with up to five 200-character blocks of surrounding text, as one
10,773-token request, and llama.cpp refused it (Deque's Mars Commuter
demo, 2026-11-19).

The first fix split pages by a fixed guess of 2.5 characters per token.
The guess was far too low for this text: section508.gov's link check went
out in up to 6 requests of about 2,300 tokens each, every one repeating
the 6,200-character instructions, and a 9-page scan queued 58 requests
(about 37 minutes of model time). Now the whole prompt is counted with
the model's own tokenizer (``count_tokens``, llama.cpp ``/tokenize``): it
goes in one request when it fits, which is the usual case, and is split
by the measured characters per token when it does not.

The answer is capped and held to a JSON schema. Without a cap the 4B
model kept writing for over two minutes on SC 2.4.6. Without a schema it
answered ``{}``, ``{{{{{{{{`` or "reasonreasonreason…" to 38 of 62
requests (section508.gov, 2026-11-19), so most of the model time found
nothing. The schema fixes the shape: a ``violations`` list of entries
with an index into this request's items, two short texts and a
confidence.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

T = TypeVar("T")

# The model's window, as the private service runs it.
CONTEXT_TOKENS = 8192
# Longest answer a wording check asks for. A violation is about 60-120
# tokens (index, explanation, suggested fix), so this fits a dozen.
ANSWER_TOKENS = 1536
# Room kept spare for the chat template around the prompt.
SPARE_TOKENS = 512
# The prompt may use the rest.
PROMPT_TOKENS = CONTEXT_TOKENS - ANSWER_TOKENS - SPARE_TOKENS
# Characters per token when the model cannot count (Ollama, or a failed
# count): the low end for quoted names and web addresses, so a guessed
# batch errs on the small side.
FALLBACK_CHARS_PER_TOKEN = 3.0
# A split by measured characters per token aims a little under the limit:
# one batch's text tokenizes a little differently from the whole page's.
SPLIT_MARGIN = 0.9
# Longest text the schema lets the model write for a reason or a fix.
MAX_TEXT_CHARS = 300


def violations_schema(count: int) -> dict[str, Any]:
    """The answer every wording check asks for, for a request of ``count`` items.

    ``index`` can only name one of this request's items, and each text is
    short, so a model cannot repeat itself until the answer runs out.
    """
    return {
        "type": "object",
        "properties": {
            "violations": {
                "type": "array",
                "maxItems": max(count, 0),
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "minimum": 0, "maximum": max(count - 1, 0)},
                        "reason": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                        "recommendation": {"type": "string", "maxLength": MAX_TEXT_CHARS},
                        "confidence": {"enum": ["high", "medium", "low"]},
                    },
                    "required": ["index", "reason", "recommendation", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["violations"],
        "additionalProperties": False,
    }


def fit_batches(
    items: Sequence[T],
    prompt_of: Callable[[list[T]], str],
    *,
    prompt_chars: int,
) -> list[list[T]]:
    """Split ``items`` into consecutive batches whose prompt is at most ``prompt_chars``.

    Each batch is measured as its whole prompt (instructions, numbering
    and all). An item too big on its own still goes, alone: the model then
    refuses that one request, not the page.
    """
    batches: list[list[T]] = []
    current: list[T] = []
    for item in items:
        trial = [*current, item]
        if current and len(prompt_of(trial)) > prompt_chars:
            batches.append(current)
            current = [item]
        else:
            current = trial
    if current:
        batches.append(current)
    return batches


async def plan_batches(
    items: Sequence[T],
    prompt_of: Callable[[list[T]], str],
    count_tokens: Callable[[str], Awaitable[int | None]],
) -> list[list[T]]:
    """The fewest requests that fit: counted once, split only when needed."""
    if not items:
        return []
    whole = prompt_of(list(items))
    tokens = await count_tokens(whole)
    if tokens is not None and tokens <= PROMPT_TOKENS:
        return [list(items)]
    chars_per_token = len(whole) / tokens if tokens else FALLBACK_CHARS_PER_TOKEN
    margin = SPLIT_MARGIN if tokens else 1.0
    return fit_batches(items, prompt_of, prompt_chars=int(PROMPT_TOKENS * chars_per_token * margin))


__all__ = [
    "ANSWER_TOKENS",
    "CONTEXT_TOKENS",
    "PROMPT_TOKENS",
    "fit_batches",
    "plan_batches",
    "violations_schema",
]
