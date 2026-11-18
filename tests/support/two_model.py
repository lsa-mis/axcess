"""A size with two models (text, and images), for tests only.

Every size Axcess offers runs one model since Extra large was removed
(2026-11-18). The runtime still starts two models when a setup names two:
a setup saved by an earlier test build, or a later size. These tests keep
that path covered with the models Extra large used.
"""

from __future__ import annotations

from audit.ai.catalog import Catalog, ModelEntry, Tier, load_catalog

TWO_MODEL = Tier(
    id="extra_large",
    label="Extra large",
    min_memory_gb=32,
    text=ModelEntry.model_validate(
        {
            "tag": "qwen2.5-coder:14b-instruct",
            "size": 8988110272,
            "licence": "Apache-2.0",
            "gguf": {
                "repo": "Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
                "revision": "d0a692ef765eefbf2fabb130b3cb2e8917e3d225",
                "file": "qwen2.5-coder-14b-instruct-q4_k_m.gguf",
                "size": 8988110272,
                "sha256": "c1e659736d89ac1065fb495330fb824d94001974a4bfa78e7270e43476a8d940",
            },
        }
    ),
    vision=ModelEntry.model_validate(
        {
            "tag": "qwen3-vl:8b-instruct",
            "size": 6186814624,
            "licence": "Apache-2.0",
            "gguf": {
                "repo": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
                "revision": "f982a07559d4a2f6c8744d840bf6fccab30eea96",
                "file": "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
                "size": 5027784800,
                "sha256": "67d1659bfe71b89d50b45a4ad1a9e5b997e5bb16ce5da66a6a6167abd569e9e2",
            },
            "mmproj": {
                "repo": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
                "revision": "f982a07559d4a2f6c8744d840bf6fccab30eea96",
                "file": "mmproj-Qwen3VL-8B-Instruct-F16.gguf",
                "size": 1159029824,
                "sha256": "ca524100ebf825c9a870db1c580d03879e0da0ab2541697e2458e64891cf9d38",
            },
        }
    ),
)


def two_model_catalog() -> Catalog:
    """The real catalogue plus the two-model size, last (the largest)."""
    catalog = load_catalog()
    return catalog.model_copy(update={"tiers": (*catalog.tiers, TWO_MODEL)})
