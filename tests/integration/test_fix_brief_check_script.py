"""The fix brief's check script, run for real on the fix brief test site.

The brief (``audit.exports.fix_brief``) tells a coding agent to check each
fix with ``axcess_check.py``: Playwright opens the page, adds the scan's
axe-core, and runs only the issue type's rule. This test does what the agent
would do, in a temporary copy of ``tests/fixtures/fix_brief_site``: save the
brief and the script, run a check before a fix (it fails), fix one problem,
and run it again (it passes), while the problems not fixed still fail.

The locators are the ones a real scan of the site saved (see
``docs/fix-brief-manual-check/``). The pages are recorded at the scan's
address and checked on a local server through ``--origin``, as an agent
checks its own copy.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from support.rich_scan import dom_finding

from audit.analyzer.axe import DEFAULT_AXE_BUNDLE
from audit.db import repo
from audit.exports import axcess_check
from audit.exports.collector import collect_scan
from audit.exports.fix_brief import CHECK_SCRIPT, render_fix_brief

pytest.importorskip("playwright.sync_api")
pytestmark = [pytest.mark.integration, pytest.mark.browser]

SITE = Path(__file__).resolve().parents[1] / "fixtures" / "fix_brief_site"
SCANNED = "http://127.0.0.1:8799"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def site(tmp_path: Path) -> Iterator[tuple[Path, str]]:
    """A copy of the test site, served on this computer only."""

    root = tmp_path / "site"
    shutil.copytree(SITE, root)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_QuietHandler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _brief(conn: sqlite3.Connection) -> str:
    cur = conn.execute(
        "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
        "VALUES (?, 'completed', 2, 0, '{}')",
        (f"{SCANNED}/index.html",),
    )
    scan_id = int(cur.lastrowid or 0)
    pages = {
        name: repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized=f"{SCANNED}/{name}",
            status_code=200,
            title="Harbor Books",
            render_mode="js",
            html_hash="a" * 64,
        )
        for name in ("index.html", "about.html")
    }
    found = [
        ("about.html", "color-contrast", ".fine-print", "serious", None),
        ("index.html", "color-contrast", "p", "serious", None),
        ("index.html", "image-alt", "img", "critical", None),
        ("index.html", "button-name", "button", "critical", "Open the cart"),
    ]
    for page, rule, target, impact, revealed_by in found:
        dom_finding(
            conn,
            scan_id=scan_id,
            page_id=pages[page],
            rule_id=rule,
            help_text=f"Rule {rule}",
            target=target,
            impact=impact,
            revealed_by=revealed_by,
        )
    return render_fix_brief(
        collect_scan(conn, scan_id),
        conn=conn,
        generated_at=datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
    )


def _place(checks: dict[str, object], rule: str, page: str) -> str:
    places = checks["places"]
    assert isinstance(places, dict)
    return next(
        key
        for key, place in places.items()
        if place["rule"] == rule and place["page"] == f"{SCANNED}/{page}"
    )


def test_a_check_fails_before_the_fix_and_passes_after_it(
    tmp_db: sqlite3.Connection, tmp_path: Path, site: tuple[Path, str]
) -> None:
    root, origin = site
    work = tmp_path / "agent"
    work.mkdir()
    brief = _brief(tmp_db)
    # What the brief tells the agent to save.
    (work / "fix-brief.md").write_text(brief, encoding="utf-8")
    (work / "axcess_check.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    shutil.copyfile(DEFAULT_AXE_BUNDLE, work / "axe.min.js")
    checks = axcess_check.load_checks(brief)
    fine_print = _place(checks, "color-contrast", "about.html")
    promo = _place(checks, "color-contrast", "index.html")
    image = _place(checks, "image-alt", "index.html")
    cart = _place(checks, "button-name", "index.html")

    def check(*args: str) -> tuple[int, str]:
        done = subprocess.run(  # noqa: S603 - this interpreter, the script Axcess wrote
            [sys.executable, "axcess_check.py", "fix-brief.md", *args, "--origin", origin],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return done.returncode, done.stdout

    # Before the fix: the rule fails at the element.
    code, out = check(fine_print)
    assert code == axcess_check.FAILED, out
    assert f"FAILED check {fine_print} (color-contrast)" in out
    assert "still failing: .fine-print" in out

    # Fix one problem, as an agent would: a darker text color (#595959 on white
    # is 7.0:1).
    css = root / "assets" / "site.css"
    css.write_text(
        css.read_text().replace(".fine-print { color: #c4c4c4;", ".fine-print { color: #595959;"),
        encoding="utf-8",
    )

    # After the fix: it passes, and running it again gives the same result.
    first = check(fine_print)
    assert first[0] == axcess_check.PASSED, first[1]
    assert first == check(fine_print)

    # The problems not fixed still fail, so a pass is not the default.
    assert check(promo)[0] == axcess_check.FAILED
    assert check(image)[0] == axcess_check.FAILED
    # The whole issue type still fails: one of its two places is not fixed.
    code, out = check(fine_print.split(".")[0])
    assert code == axcess_check.FAILED, out
    assert f"PASSED check {fine_print}" in out and f"FAILED check {promo}" in out
    # A place that appears only after a click is never reported as passed.
    code, out = check(cart)
    assert code == axcess_check.NOT_CHECKED, out

    # If the element is gone, the script cannot say the rule passes there.
    index = root / "index.html"
    index.write_text(
        index.read_text().replace('<img src="assets/cover.png" class="cover-art"', "<span"),
        encoding="utf-8",
    )
    code, out = check(image)
    assert code == axcess_check.NOT_CHECKED, out
    assert "no longer found" in out


def test_a_different_axe_core_version_is_not_checked(
    tmp_db: sqlite3.Connection, tmp_path: Path, site: tuple[Path, str]
) -> None:
    _, origin = site
    work = tmp_path / "agent"
    work.mkdir()
    brief = _brief(tmp_db)
    (work / "fix-brief.md").write_text(brief, encoding="utf-8")
    (work / "axcess_check.py").write_text(CHECK_SCRIPT, encoding="utf-8")
    # The scan's bundle, with its version string changed.
    bundle = DEFAULT_AXE_BUNDLE.read_text(encoding="utf-8")
    version = axcess_check.load_checks(brief)["axe_version"]
    (work / "axe.min.js").write_text(bundle.replace(f'"{version}"', '"0.0.1"'), encoding="utf-8")
    place = _place(axcess_check.load_checks(brief), "image-alt", "index.html")

    done = subprocess.run(  # noqa: S603 - this interpreter, the script Axcess wrote
        [sys.executable, "axcess_check.py", "fix-brief.md", place, "--origin", origin],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert done.returncode == axcess_check.NOT_CHECKED, done.stdout
    assert "axe-core 0.0.1, the scan used" in done.stdout
