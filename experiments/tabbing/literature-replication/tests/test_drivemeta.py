"""Tests for the Drive listing metadata parser and the byte-capped fetcher.

Written before the implementation. Slice 1 covers pure parsing and the byte
cap; no network is touched by any test here.
"""

from __future__ import annotations

import pytest

from tools import drivemeta


# --------------------------------------------------------------------------
# parse_listing: name -> id, from the real shape of Drive's folder HTML
# --------------------------------------------------------------------------

# Trimmed to the two attributes the parser relies on, in the order Drive emits
# them: a per-item container carrying data-id, then the aria-label naming it.
_LISTING = """
<div data-id="_gd"></div>
<c-wiz>
  <div data-id="1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA" aria-label="battlenet Shared folder">
    <div aria-label="Size not available"></div>
  </div>
  <div data-id="1BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB" aria-label="citiprogram Binary Shared">
    <div aria-label="Size: 347 KB&#10;Storage used: 347 KB"></div>
  </div>
  <div data-id="1CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC" aria-label="craigslist Binary Shared">
    <div aria-label="Size: 284 KB&#10;Storage used: 284 KB"></div>
  </div>
</c-wiz>
"""


def test_parse_listing_maps_names_to_ids():
    entries = drivemeta.parse_listing(_LISTING)
    by_name = {e.name: e.file_id for e in entries}
    assert by_name == {
        "battlenet": "1AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "citiprogram": "1BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
        "craigslist": "1CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
    }


def test_parse_listing_marks_folders_and_files():
    entries = {e.name: e for e in drivemeta.parse_listing(_LISTING)}
    assert entries["battlenet"].is_folder is True
    assert entries["citiprogram"].is_folder is False


def test_parse_listing_records_reported_size_text():
    entries = {e.name: e for e in drivemeta.parse_listing(_LISTING)}
    assert entries["citiprogram"].size_text == "347 KB"
    assert entries["battlenet"].size_text is None


def test_parse_listing_skips_the_sentinel_id():
    assert all(e.file_id != "_gd" for e in drivemeta.parse_listing(_LISTING))


def test_parse_listing_is_empty_on_unrelated_html():
    assert drivemeta.parse_listing("<html><body>nope</body></html>") == []


# The token order Drive actually emits, captured from the live KAFE_60_subjects
# listing on 2026-09-14: the item id repeats three times, once *after* the name
# label, and a bare "Shared" plus a "Modified ..." label sit between the name
# and the size. An earlier parser lost every item to the third id.
_REAL_SHAPE = """
<div data-id="10OAmVr5JWib_u2SXrkMJUtkTD_zq6htw"></div>
<div data-id="10OAmVr5JWib_u2SXrkMJUtkTD_zq6htw"></div>
<div aria-label="carlsjr Binary Shared"></div>
<div data-id="10OAmVr5JWib_u2SXrkMJUtkTD_zq6htw"></div>
<div aria-label="Shared"></div>
<div aria-label="Modified Jun 9, 2021"></div>
<div aria-label="Size: 2 MB&#10;Storage used: 2 MB"></div>
<div aria-label="More actions"></div>
<div aria-label="Download"></div>
<div data-id="1ECmdsdNts4ESRiCMOwAOInqygpxLkKEb"></div>
<div data-id="1ECmdsdNts4ESRiCMOwAOInqygpxLkKEb"></div>
<div aria-label="citiprogram Binary Shared"></div>
<div data-id="1ECmdsdNts4ESRiCMOwAOInqygpxLkKEb"></div>
<div aria-label="Shared"></div>
<div aria-label="Modified Jun 9, 2021"></div>
<div aria-label="Size: 347 KB&#10;Storage used: 347 KB"></div>
<div data-id="1FolderFolderFolderFolderFolderX"></div>
<div aria-label="battlenet Shared folder"></div>
<div aria-label="Modified Oct 16, 2021"></div>
<div aria-label="Size not available"></div>
"""


def test_parse_listing_handles_the_real_repeated_id_shape():
    entries = {e.name: e for e in drivemeta.parse_listing(_REAL_SHAPE)}
    assert set(entries) == {"carlsjr", "citiprogram", "battlenet"}
    assert entries["citiprogram"].file_id == "1ECmdsdNts4ESRiCMOwAOInqygpxLkKEb"
    assert entries["citiprogram"].size_text == "347 KB"
    assert entries["carlsjr"].size_text == "2 MB"


def test_parse_listing_real_shape_marks_folder_without_size():
    entries = {e.name: e for e in drivemeta.parse_listing(_REAL_SHAPE)}
    assert entries["battlenet"].is_folder is True
    assert entries["battlenet"].size_text is None


# --------------------------------------------------------------------------
# ByteBudget: the download cap Harry authorized
# --------------------------------------------------------------------------


def test_budget_allows_spend_under_cap():
    budget = drivemeta.ByteBudget(limit=1000)
    budget.spend(400)
    budget.spend(500)
    assert budget.used == 900
    assert budget.remaining == 100


def test_budget_refuses_to_exceed_cap():
    budget = drivemeta.ByteBudget(limit=1000)
    budget.spend(900)
    with pytest.raises(drivemeta.BudgetExceeded):
        budget.spend(200)
    # The refused spend is not recorded.
    assert budget.used == 900


def test_budget_check_rejects_a_declared_size_before_any_bytes_move():
    budget = drivemeta.ByteBudget(limit=1000)
    with pytest.raises(drivemeta.BudgetExceeded):
        budget.check(1001)
    assert budget.used == 0
