"""Tests for ``audit.analyzer.model_registry``.

The contract this pins:

  * Per-criterion picks override the kind-default.
  * Unknown criteria fall through to the kind-default.
  * Missing/broken YAML never raises — the registry returns a hard
    fallback so the analyzer pipeline can still run.
  * ``fetch_set("required" | "recommended")`` returns YAML-declared
    tags; ``all_fetch_tags()`` is the deduped union.
"""

from __future__ import annotations

from audit.analyzer import model_registry


def test_known_criterion_returns_pinned_model() -> None:
    """A criterion with an explicit `primary` entry returns that tag."""
    model_registry.reset_cache()
    pick = model_registry.get_pick("1.4.5")
    # SC 1.4.5 is pinned to the small Qwen3-VL instruct model — this
    # is our current default for the image-of-text pipeline. If the
    # YAML moves to something else, update this expectation; pinning
    # the test ensures the override path is actually being honored.
    assert pick.primary == "qwen3-vl:2b-instruct"
    assert pick.kind == "vision"


def test_unknown_criterion_falls_through_to_default() -> None:
    """A criterion not in the YAML returns the kind-default.

    Note: we don't pin the exact tag here — it changes during demo
    setup (gemma2 vs qwen2.5). We assert the SHAPE: a non-empty
    string that's not a comment placeholder.
    """
    model_registry.reset_cache()
    pick = model_registry.get_pick("9.9.9", kind="text")
    assert pick.primary  # non-empty
    assert ":" in pick.primary  # looks like an Ollama tag (name:variant)
    assert pick.kind == "text"


def test_no_sc_uses_kind_default() -> None:
    """Calling without a criterion still works if the kind is given."""
    model_registry.reset_cache()
    pick = model_registry.get_pick(None, kind="code")
    assert pick.primary == "qwen2.5-coder:7b-instruct"
    assert pick.kind == "code"


def test_kind_normalization() -> None:
    """A bogus `kind` string normalizes to ``"text"`` (the safe default)."""
    model_registry.reset_cache()
    pick = model_registry.get_pick(None, kind="nonsense-kind")  # type: ignore[arg-type]
    assert pick.kind == "text"


def test_fetch_set_tiers() -> None:
    """The required tier is the minimum; recommended is a strict superset."""
    model_registry.reset_cache()
    required = model_registry.fetch_set("required")
    recommended = model_registry.fetch_set("recommended")
    assert len(required) >= 1
    # Qwen3-VL 2B instruct is our image-of-text default — it must
    # remain in the required tier so a fresh setup still works.
    assert "qwen3-vl:2b-instruct" in required
    # Recommended must include things beyond required (otherwise the
    # tier distinction is pointless).
    assert any(tag not in required for tag in recommended)


def test_all_fetch_tags_is_deduped() -> None:
    """``all_fetch_tags`` returns each tag at most once."""
    model_registry.reset_cache()
    tags = model_registry.all_fetch_tags()
    assert len(tags) == len(set(tags))


def test_model_pick_carries_rationale_when_present() -> None:
    """Per-criterion entries with `rationale` text round-trip into the dataclass."""
    model_registry.reset_cache()
    pick = model_registry.get_pick("2.5.3")
    # Specifically pinned in the YAML with a non-trivial rationale.
    assert pick.rationale is not None
    assert len(pick.rationale) > 10
