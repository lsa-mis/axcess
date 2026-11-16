"""Measure AI fix suggestions against a fixed set of sample cases.

Opt-in and local: it needs Ollama running with the suggestion text model
installed, and it sends nothing anywhere else. For each case it builds the
same prompt the feature uses, asks the model, and records whether the answer
was usable and safe, and whether the one axe rule passes on the suggested
code. Run it after changing the prompt or the model:

    make suggest-eval

It prints a table and exits non-zero when any answer is unsafe, because an
unsafe answer is never acceptable; the other numbers are for people to read.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from audit.config import get_settings
from audit.suggest.context import EvidenceBundle
from audit.suggest.models import ModelAnswerV2
from audit.suggest.provider import (
    OllamaSuggestionProvider,
    SuggestionError,
    build_prompt,
    parse_answer,
    prompt_version,
)
from audit.suggest.verify import AxeFragmentVerifier, check_options

DEFAULT_CASES = Path("tests/quality/suggest/cases_v1.yaml")


@dataclass
class CaseResult:
    name: str
    outcome: str
    check: str
    seconds: float


def _bundle(case: dict[str, Any]) -> EvidenceBundle:
    return EvidenceBundle(
        scan_id=0,
        page_id=0,
        occurrence_kind="a11y",
        occurrence_id=0,
        pipeline=str(case.get("pipeline", "axe")),
        rule_id=str(case["rule_id"]),
        issue_title=str(case["issue_title"]),
        wcag_sc=case.get("wcag_sc"),
        page_url="https://example.com/",
        problem=str(case["problem"]),
        snippet=case.get("snippet"),
        selector=None,
        nearby_text=case.get("nearby_text"),
        fix_steps=(),
        check_rule_id=str(case["rule_id"]) if case.get("pipeline", "axe") == "axe" else None,
    )


async def _run(cases: list[dict[str, Any]], model: str) -> list[CaseResult]:
    settings = get_settings()
    verifier = AxeFragmentVerifier()
    results: list[CaseResult] = []
    async with httpx.AsyncClient() as client:
        provider = OllamaSuggestionProvider(
            client, base_url=settings.ollama_base_url, timeout_s=settings.suggestion_timeout_s
        )
        for case in cases:
            bundle = _bundle(case)
            started = time.monotonic()
            check = "-"
            try:
                raw = await provider.generate(build_prompt(bundle), model=model, image=None)
                answer = parse_answer(raw)
                outcome = "ok"
                if not isinstance(answer, ModelAnswerV2):
                    raise SuggestionError(
                        "bad_answer", "The model did not return two code options."
                    )
                checks = await check_options(
                    verifier, bundle.check_rule_id, answer.developer.options
                )
                check = "/".join(checks)
            except SuggestionError as exc:
                outcome = exc.code if exc.code != "bad_answer" else f"bad_answer: {exc.detail}"
            results.append(CaseResult(case["name"], outcome, check, time.monotonic() - started))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--model", default=None, help="Ollama model; default: the setting")
    args = parser.parse_args(argv)
    cases = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    model = args.model or get_settings().suggestion_text_model
    results = asyncio.run(_run(cases, model))

    print(f"Model: {model}   Prompt: {prompt_version()}   Cases: {len(results)}")
    print(f"{'case':32} {'answer':40} {'rule check':12} seconds")
    for r in results:
        print(f"{r.name:32} {r.outcome[:40]:40} {r.check:12} {r.seconds:6.1f}")
    usable = sum(r.outcome == "ok" for r in results)
    passed = sum(all(c == "passed" for c in r.check.split("/")) for r in results)
    unsafe = [r for r in results if "could run" in r.outcome]
    print(f"\nUsable answers: {usable}/{len(results)}   Rule check passed: {passed}/{len(results)}")
    if unsafe:
        print(f"Unsafe answers (refused, never shown): {len(unsafe)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
