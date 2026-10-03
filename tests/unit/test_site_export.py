"""The public site's data export must match the product's coverage source of truth.

``site/export_data.py`` writes the numbers and criterion cards the Astro site
renders. If it drifted from ``audit.coverage_matrix``, the site would claim
coverage the code does not have.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def _export_module() -> ModuleType:
    # Loaded by path under its own name: "site" is a standard-library module.
    spec = importlib.util.spec_from_file_location(
        "site_export_data", ROOT / "site" / "export_data.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_export_matches_the_matrix() -> None:
    from audit import coverage_matrix

    data = _export_module().coverage()
    summ = coverage_matrix.summary()
    crit = coverage_matrix.load_matrix()

    assert data["summary"]["total"] == summ.total == len(crit)
    assert data["summary"]["covered"] == summ.covered
    assert data["summary"]["manualOnly"] == summ.manual_only
    assert data["summary"]["byMethod"] == summ.by_method
    assert [c["sc"] for c in data["criteria"]] == [c.sc for c in crit]
    for exported, source in zip(data["criteria"], crit, strict=True):
        assert exported["method"] == source.method, source.sc
        assert exported["manualCheck"] == source.manual_check, source.sc


def test_every_criterion_says_what_a_person_must_check() -> None:
    for c in _export_module().coverage()["criteria"]:
        assert c["manualCheck"].strip(), c["sc"]
