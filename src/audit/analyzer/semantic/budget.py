"""How much one wording-check request may carry, and how long its answer may be.

The private llama.cpp service gives each request an 8,192-token window
(``audit.ai.runtime.CONTEXT_TOKENS``), shared by the prompt and the
answer. A link-heavy page used to overflow it: SC 2.4.4 sent 50 links,
each with up to five 200-character blocks of surrounding text, as one
10,773-token request, and llama.cpp refused it (Deque's Mars Commuter
demo, 2026-11-19). Now a page's links or headings go in as many requests
as it takes, each sized to fit.

The answer is capped too. Without a cap the 4B model kept writing for
over two minutes on SC 2.4.6 (about 2,500 tokens by each timeout, the
same page), so the check timed out three times and held the crawl about
six minutes. A capped answer that runs out mid-JSON fails at once, as
"did not return valid JSON", and the crawl moves on.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")

# The model's window, as the private service runs it.
CONTEXT_TOKENS = 8192
# Longest answer a wording check asks for. A violation is about 60-120
# tokens (index, explanation, suggested fix), so this fits a dozen.
ANSWER_TOKENS = 1536
# Room kept spare for the chat template and the tokenizer's surprises.
SPARE_TOKENS = 512
# Characters per token, the low end for this text (quoted names, web
# addresses, page text), so a batch errs on the small side.
CHARS_PER_TOKEN = 2.5
PROMPT_CHARS = int((CONTEXT_TOKENS - ANSWER_TOKENS - SPARE_TOKENS) * CHARS_PER_TOKEN)


def fit_batches(
    items: Sequence[T],
    render: Callable[[list[T]], str],
    template: str,
    *,
    prompt_chars: int = PROMPT_CHARS,
) -> list[list[T]]:
    """Split ``items`` into consecutive batches whose prompt fits the window.

    ``render`` turns a batch into the text that goes into ``template``;
    each batch is measured as rendered, numbering included. An item too
    big on its own still goes, alone: the model then refuses that one
    request, not the page.
    """
    room = prompt_chars - len(template)
    batches: list[list[T]] = []
    current: list[T] = []
    for item in items:
        trial = [*current, item]
        if current and len(render(trial)) > room:
            batches.append(current)
            current = [item]
        else:
            current = trial
    if current:
        batches.append(current)
    return batches


__all__ = ["ANSWER_TOKENS", "CONTEXT_TOKENS", "PROMPT_CHARS", "fit_batches"]
