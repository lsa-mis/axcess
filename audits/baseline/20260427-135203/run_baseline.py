"""Phase-1 baseline accessibility scanner.

Spins up the FastAPI app against a seeded tmp DB, walks every public route
in both the React SPA (mounted at ``/app``) and the legacy Jinja UI, runs
axe-core against each page with a *broader* tag set than the in-tree test
(which only covers ``wcag2a`` + ``wcag2aa``), and dumps the raw violations
JSON to this directory.

Why a separate script and not just pytest?

* The transformation target is **WCAG 2.2 AAA**. The existing
  ``test_accessibility_axe.py`` filters axe to ``wcag2a, wcag2aa`` only;
  re-running it gives us no new information. We want the AAA-tagged rules
  in the report so we can quantify the gap.
* The audit lives in ``audits/baseline/<ts>/`` — keeping the runner next
  to its output makes it trivial to reproduce later (``python
  run_baseline.py``) without wrestling with pytest discovery.
* Fails-soft: a missing route or empty seed shouldn't block the audit.
  Each route is wrapped; any error is captured into the per-route JSON.

Outputs (next to this script):

* ``violations.json`` — list of ``{route, ui, violations: [...]}`` records
* ``summary.md``     — human-readable summary, sorted by impact
* ``run.log``        — stdout/stderr from the run
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Make the repo's tests-conftest seeders importable without pytest.
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import uvicorn  # noqa: E402

from audit.blob_store import BlobStore  # noqa: E402
from audit.db import repo  # noqa: E402
from audit.db.schema import connect  # noqa: E402
from audit.synthesizer.findings import synthesize_findings  # noqa: E402
from audit.web.server import create_app  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
AXE_PATH = REPO_ROOT / "src" / "audit" / "web" / "static" / "axe.min.js"

# Tags we want axe to check. Includes AAA (the actual target) plus the
# best-practice rules that catch idioms the spec leaves loose.
AXE_TAGS = [
    "wcag2a",
    "wcag2aa",
    "wcag2aaa",
    "wcag21a",
    "wcag21aa",
    "wcag22aa",
    "best-practice",
]


@dataclass
class RouteResult:
    ui: str  # "spa" | "jinja"
    route: str
    url: str
    error: str | None = None
    violations: list[dict[str, Any]] = field(default_factory=list)


def _pixel_png(color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (40, 40), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _seed_db(tmp_dir: Path) -> tuple[Path, Path, int]:
    """Create a tmp DB + blob store with one completed scan, two findings."""
    db_path = tmp_dir / "audit.db"
    blob_dir = tmp_dir / "blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        migrations = REPO_ROOT / "src" / "audit" / "db" / "migrations"
        for path in sorted(migrations.glob("*.sql")):
            conn.executescript(path.read_text())

        store = BlobStore(blob_dir)
        cur = conn.execute(
            "INSERT INTO scans (seed_url, status, page_count, finding_count, config_json) "
            "VALUES ('http://example.com/', 'completed', 2, 0, '{}')"
        )
        scan_id = int(cur.lastrowid or 0)

        page_a = repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized="http://example.com/",
            status_code=200,
            title="Home",
            render_mode="static",
            html_hash="0" * 64,
        )
        page_b = repo.upsert_page(
            conn,
            scan_id=scan_id,
            url_normalized="http://example.com/about",
            status_code=200,
            title="About",
            render_mode="static",
            html_hash="1" * 64,
        )
        png = _pixel_png()
        png_hash, png_rel = store.store(png, "image/png")
        banner_id = repo.upsert_image(
            conn,
            content_hash=png_hash,
            src_url="http://example.com/banner.png",
            mime="image/png",
            bytes_len=len(png),
            width=40,
            height=40,
            blob_path=png_rel,
            has_svg_text=False,
            scan_id=scan_id,
        )
        repo.upsert_page_image(
            conn,
            page_id=page_a,
            image_id=banner_id,
            alt_text=None,
            role=None,
            context_snippet="Buy our widgets",
            position=0,
            above_fold=True,
        )
        repo.upsert_page_image(
            conn,
            page_id=page_b,
            image_id=banner_id,
            alt_text=None,
            role=None,
            context_snippet="Buy our widgets",
            position=1,
            above_fold=False,
        )
        repo.upsert_analysis(
            conn,
            image_id=banner_id,
            ocr_text="BUY OUR WIDGETS TODAY",
            ocr_confidence=92.5,
            vlm_classification="essential",
            vlm_rationale="Clearly text-as-image promoting an offer.",
            has_text=True,
            model_versions={"ocr": "tesseract-test", "vlm": "stub:1", "prompt": "v1-stub"},
        )
        synthesize_findings(conn, scan_id=scan_id)
        return db_path, blob_dir, scan_id
    finally:
        conn.close()


def _start_server(db_path: Path, blob_dir: Path) -> tuple[uvicorn.Server, threading.Thread, int]:
    app = create_app(db_path=db_path, blob_dir=blob_dir)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started and server.servers:
            break
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("uvicorn failed to start")
    sock = server.servers[0].sockets[0]
    return server, thread, int(sock.getsockname()[1])


async def _scan_route(page: Any, axe_text: str, base: str, ui: str, route: str) -> RouteResult:
    url = f"{base}{route}"
    result = RouteResult(ui=ui, route=route, url=url)
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
        await page.add_script_tag(content=axe_text)
        violations = await page.evaluate(
            """async (tags) => {
                const r = await window.axe.run(document, {
                    runOnly: { type: 'tag', values: tags }
                });
                return r.violations;
            }""",
            AXE_TAGS,
        )
        result.violations = list(violations)
    except Exception as exc:  # noqa: BLE001
        result.error = f"{type(exc).__name__}: {exc}"
    return result


async def _run_all(base: str, scan_id: int) -> list[RouteResult]:
    from playwright.async_api import async_playwright

    axe_text = AXE_PATH.read_text(encoding="utf-8")
    routes: list[tuple[str, str]] = [
        # SPA — every top-level route the React Router knows about.
        ("spa", "/app/"),
        ("spa", "/app/scans"),
        ("spa", "/app/scans/new"),
        ("spa", f"/app/scans/{scan_id}"),
        ("spa", f"/app/scans/{scan_id}/findings"),
        # Jinja legacy UI.
        ("jinja", "/scans"),
        ("jinja", "/scans/new"),
        ("jinja", f"/scans/{scan_id}"),
        ("jinja", f"/scans/{scan_id}/findings"),
        ("jinja", "/pages/1"),
    ]
    results: list[RouteResult] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            for ui, route in routes:
                print(f"  scan {ui:6s} {route} … ", end="", flush=True)
                r = await _scan_route(page, axe_text, base, ui, route)
                if r.error:
                    print(f"ERROR ({r.error})")
                else:
                    print(f"{len(r.violations)} violations")
                results.append(r)
        finally:
            await browser.close()
    return results


def _write_outputs(results: list[RouteResult]) -> None:
    raw = [
        {
            "ui": r.ui,
            "route": r.route,
            "url": r.url,
            "error": r.error,
            "violation_count": len(r.violations),
            "violations": r.violations,
        }
        for r in results
    ]
    (OUT_DIR / "violations.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")

    # Roll up an aggregate by rule id + impact for the summary table.
    by_rule: dict[str, dict[str, Any]] = {}
    for r in results:
        for v in r.violations:
            rid = v.get("id", "?")
            entry = by_rule.setdefault(
                rid,
                {
                    "id": rid,
                    "impact": v.get("impact"),
                    "help": v.get("help"),
                    "helpUrl": v.get("helpUrl"),
                    "tags": v.get("tags", []),
                    "routes": [],
                    "node_count": 0,
                },
            )
            entry["routes"].append(f"{r.ui}:{r.route}")
            entry["node_count"] += len(v.get("nodes", []))

    impact_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3, None: 4}
    rules = sorted(
        by_rule.values(),
        key=lambda e: (impact_order.get(e["impact"], 5), -e["node_count"]),
    )

    md = ["# Baseline a11y scan — raw axe-core results", ""]
    md.append(
        f"Tags scanned: `{', '.join(AXE_TAGS)}` "
        f"(includes WCAG 2.2 AAA, the actual transformation target)."
    )
    md.append("")
    md.append("## Per-route counts")
    md.append("")
    md.append("| UI | Route | Violations | Error |")
    md.append("|----|-------|-----------:|-------|")
    for r in results:
        md.append(
            f"| {r.ui} | `{r.route}` | "
            f"{'—' if r.error else len(r.violations)} | "
            f"{r.error or ''} |"
        )
    md.append("")
    md.append("## Unique rules failed (across all routes)")
    md.append("")
    if not rules:
        md.append("_No violations reported._")
    else:
        md.append(
            "| Rule | Impact | Nodes | Tags | Help |"
        )
        md.append(
            "|------|--------|------:|------|------|"
        )
        for e in rules:
            tag_str = ", ".join(t for t in e["tags"] if t.startswith("wcag"))
            md.append(
                f"| `{e['id']}` | {e['impact'] or '—'} | {e['node_count']} | "
                f"{tag_str} | [{e['help']}]({e['helpUrl']}) |"
            )
    (OUT_DIR / "summary.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    print(f"baseline a11y scan → {OUT_DIR}")
    if not AXE_PATH.exists():
        sys.exit(f"axe-core bundle not found at {AXE_PATH}")

    import tempfile

    with tempfile.TemporaryDirectory(prefix="audit-baseline-") as tmp:
        tmp_path = Path(tmp)
        print(f"  seeding tmp DB at {tmp_path}")
        db_path, blob_dir, scan_id = _seed_db(tmp_path)
        print(f"  starting uvicorn …")
        server, thread, port = _start_server(db_path, blob_dir)
        base = f"http://127.0.0.1:{port}"
        try:
            print(f"  server up at {base}, scan_id={scan_id}")
            results = asyncio.run(_run_all(base, scan_id))
        finally:
            server.should_exit = True
            thread.join(timeout=5)

    _write_outputs(results)
    total = sum(len(r.violations) for r in results)
    errors = sum(1 for r in results if r.error)
    print(f"\nwrote violations.json + summary.md")
    print(f"total violations: {total}; route errors: {errors}")


if __name__ == "__main__":
    main()
