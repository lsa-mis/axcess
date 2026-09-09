"""Loading and verifying the frozen corpus.

The corpus was authored by a different agent under a no-reading protocol, and
its labels were frozen with a manifest *before* any detector was scored. This
module is the only thing that opens it, and it opens it to verify, not to tune.

Verification is not ceremony. If a fixture changed after freezing, every number
downstream describes a corpus that no longer exists, and the honest response is
to stop rather than publish. :func:`verify_manifest` therefore raises.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ground-truth labels. Only ``violation`` is a positive.
LABELS = ("violation", "ok", "decoy", "excluded")


@dataclass(frozen=True)
class Probe:
    """One labelled element in the corpus."""

    probe_id: str
    page: str
    label: str
    cohort: str
    labels_by_viewport: dict[str, str]

    def label_for(self, viewport: str) -> str:
        """The label that applies at this viewport, falling back to the default.

        Per-viewport labels exist because a menu that is a hover-only dropdown on
        desktop can be a tap-to-open accordion on mobile: same markup, different
        correct answer. Upstream scored one viewport and flagged this as a known
        limitation they could not close.
        """
        return self.labels_by_viewport.get(viewport, self.label)


@dataclass(frozen=True)
class Corpus:
    """The frozen fixture corpus: pages, probes, and the hash that pins it."""

    root: Path
    probes: dict[str, Probe]
    pages: dict[str, list[str]]
    corpus_sha256: str

    def truth_for(self, viewport: str) -> dict[str, str]:
        """Probe id -> label at this viewport, for :func:`score_outcomes`."""
        return {pid: p.label_for(viewport) for pid, p in self.probes.items()}

    def probes_on(self, page: str) -> list[str]:
        return self.pages.get(page, [])

    def cohort_of(self, probe_id: str) -> str:
        probe = self.probes.get(probe_id)
        return probe.cohort if probe else "unknown"


def compute_corpus_sha256(files: dict[str, str]) -> str:
    """Re-derive the corpus hash from the manifest's file map.

    Must match the freezing recipe exactly: ``json.dumps`` with sorted keys and
    no whitespace, hashed as UTF-8.
    """
    payload = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(fixtures_root: Path, manifest_path: Path) -> str:
    """Check every frozen file still hashes to its recorded value.

    Returns the manifest's ``corpus_sha256``. Raises if anything drifted, is
    missing, or if the recorded corpus hash does not match its own file map —
    the last case catching a manifest edited after the fact.
    """
    manifest: dict[str, Any] = json.loads(manifest_path.read_text())
    files: dict[str, str] = manifest["files"]

    missing: list[str] = []
    changed: list[str] = []
    for rel, expected in sorted(files.items()):
        path = fixtures_root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        if sha256_file(path) != expected:
            changed.append(rel)

    if missing or changed:
        raise RuntimeError(
            "frozen corpus does not match its manifest; refusing to score. "
            f"missing={missing} changed={changed}"
        )

    recorded = str(manifest["corpus_sha256"])
    recomputed = compute_corpus_sha256(files)
    if recorded != recomputed:
        raise RuntimeError(
            "manifest corpus_sha256 does not match its own file map "
            f"(recorded={recorded} recomputed={recomputed}); the manifest was edited"
        )
    return recorded


def load_corpus(fixtures_root: Path) -> Corpus:
    """Verify the freeze, then load the labels."""
    corpus_sha = verify_manifest(fixtures_root, fixtures_root / "frozen-manifest.json")
    truth: dict[str, Any] = json.loads((fixtures_root / "truth.json").read_text())

    pages: dict[str, list[str]] = {
        page: list(ids) for page, ids in dict(truth.get("pages", {})).items()
    }
    page_of: dict[str, str] = {pid: page for page, ids in pages.items() for pid in ids}

    probes: dict[str, Probe] = {}
    for probe_id, raw in dict(truth.get("probes", {})).items():
        label = str(raw.get("label", ""))
        if label not in LABELS:
            raise RuntimeError(f"probe {probe_id} has unknown label {label!r}")
        probes[probe_id] = Probe(
            probe_id=probe_id,
            page=page_of.get(probe_id, ""),
            label=label,
            cohort=str(raw.get("cohort", "upstream")),
            labels_by_viewport={
                str(k): str(v) for k, v in dict(raw.get("labels_by_viewport", {})).items()
            },
        )

    if len(page_of) != sum(len(ids) for ids in pages.values()):
        raise RuntimeError("a probe occurs more than once in the page lists")
    unlisted = sorted(set(probes) - set(page_of))
    if unlisted:
        raise RuntimeError(f"labels reference probes with no page: {unlisted}")
    for probe in probes.values():
        if any(label not in LABELS for label in probe.labels_by_viewport.values()):
            raise RuntimeError(f"probe {probe.probe_id} has an unknown viewport label")
    orphans = sorted(set(page_of) - set(probes))
    if orphans:
        raise RuntimeError(f"pages reference probes with no label: {orphans}")

    return Corpus(root=fixtures_root, probes=probes, pages=pages, corpus_sha256=corpus_sha)
