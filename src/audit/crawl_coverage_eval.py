"""Crawl-coverage evaluation: does a scan find every page under its start?

Serves ``tests/fixtures/site/coverage`` on a loopback port, runs the real
crawler against it, and scores the result against the site's own answer key
(``expected.json``): the pages a scan of ``/docs/`` should visit, and the 9
hard cases from the crawl-coverage ticket.

Scores:

* **Recall**: expected pages visited, divided by expected pages.
* **Wrong pages**: page rows that are not an expected page (out of scope,
  blocked, a search result) or repeat one (the same page twice under URL
  variants), plus any request the server saw for a page that must never be
  requested. Target 0.
* **Efficiency**: requests the server answered for page documents, divided by
  the unique pages found. robots.txt and sitemap files are not pages and are
  counted separately. Also the seconds until 90% of expected pages had been
  requested.
* **Honesty**: the scan's stored "not visited" counts. With the default depth
  limit the 11-step page must be counted under the depth limit, and the
  sign-out link and the robots.txt page under blocked; with a small page
  limit, every counted page must be a real expected page.

The server is the evaluation's own, not the stdlib one used by other
fixtures: it answers the site's redirects, matches paths without regard to
letter case (as many real servers do, which is what makes ``/About.html`` a
duplicate rather than a broken link), fills the server origin into robots.txt
and sitemaps, and logs every request so efficiency is measured where the
target site would feel it.

The crawls are plain-HTTP crawls (no browser). Production scans render each
page in a browser too, which is a second request per page unless
``skip_static_when_rendering`` is on; this evaluation does not measure that.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from audit.crawler import url_policy
from audit.crawler.orchestrator import CrawlConfig, CrawlSummary, run_crawl
from audit.db import crawl_coverage
from audit.db.schema import connect

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "db" / "migrations"
_TEMPLATED_SUFFIXES = (".txt", ".xml")
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".xml": "application/xml",
    ".txt": "text/plain; charset=utf-8",
    ".json": "application/json",
}


class CoverageEvalError(ValueError):
    """The coverage evaluation's configuration or answer key is invalid."""


@dataclass(frozen=True, slots=True)
class CoverageEvalConfig:
    """Where the test site is, how to crawl it, and the pass marks."""

    site_dir: Path
    full_max_depth: int
    capped_max_pages: int
    min_recall: float
    max_wrong_pages: int
    max_fetches_per_page: float


@dataclass(frozen=True, slots=True)
class HardCase:
    id: str
    label: str
    must_visit: tuple[str, ...] = ()
    must_not_request: tuple[str, ...] = ()
    must_be_sitemap_only: tuple[str, ...] = ()
    single_page_rows: tuple[str, ...] = ()
    must_not_request_query: tuple[str, ...] = ()
    counts_as_blocked: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerKey:
    start_path: str
    redirects: dict[str, str]
    expected_pages: tuple[str, ...]
    hard_cases: tuple[HardCase, ...]


@dataclass
class _RequestLog:
    started: float = field(default_factory=time.monotonic)
    entries: list[tuple[float, str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, raw_path: str) -> None:
        with self.lock:
            self.entries.append((time.monotonic() - self.started, raw_path))

    def snapshot(self) -> list[tuple[float, str]]:
        with self.lock:
            return list(self.entries)


def parse_coverage_config(raw: dict[str, Any], root: Path) -> CoverageEvalConfig:
    """Validate the ``crawl_coverage`` block of the detection-eval config."""

    def number(name: str) -> float:
        value = raw.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise CoverageEvalError(f"crawl_coverage.{name} must be a non-negative number")
        return float(value)

    site = raw.get("site")
    if not isinstance(site, str) or not site:
        raise CoverageEvalError("crawl_coverage.site must be a path")
    site_dir = Path(site) if Path(site).is_absolute() else root / site
    return CoverageEvalConfig(
        site_dir=site_dir,
        full_max_depth=int(number("full_max_depth")),
        capped_max_pages=int(number("capped_max_pages")),
        min_recall=number("min_recall"),
        max_wrong_pages=int(number("max_wrong_pages")),
        max_fetches_per_page=number("max_fetches_per_page"),
    )


def load_answer_key(site_dir: Path) -> AnswerKey:
    try:
        raw = json.loads((site_dir / "expected.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverageEvalError(f"could not read the answer key: {exc}") from exc
    if raw.get("schema_version") != 1:
        raise CoverageEvalError("expected.json must use schema_version 1")
    cases = tuple(
        HardCase(
            id=str(case["id"]),
            label=str(case["label"]),
            **{
                key: tuple(case.get(key, ()))
                for key in (
                    "must_visit",
                    "must_not_request",
                    "must_be_sitemap_only",
                    "single_page_rows",
                    "must_not_request_query",
                    "counts_as_blocked",
                )
            },
        )
        for case in raw["hard_cases"]
    )
    return AnswerKey(
        start_path=str(raw["start_path"]),
        redirects={str(k): str(v) for k, v in raw.get("redirects", {}).items()},
        expected_pages=tuple(str(p) for p in raw["expected_pages"]),
        hard_cases=cases,
    )


def run_coverage_eval(config: CoverageEvalConfig) -> dict[str, Any]:
    """Crawl the test site three ways and score it. Never raises on a low score."""

    key = load_answer_key(config.site_dir)
    with _serve(config.site_dir, key) as (origin, log):
        full = _crawl(origin, key, max_depth=config.full_max_depth, max_pages=500)
        full_requests = log.snapshot()
    with _serve(config.site_dir, key) as (origin_d, _log_d):
        default = _crawl(origin_d, key, max_depth=CrawlConfig.max_depth, max_pages=500)
    with _serve(config.site_dir, key) as (origin_c, _log_c):
        capped = _crawl(
            origin_c, key, max_depth=config.full_max_depth, max_pages=config.capped_max_pages
        )

    expected = {_page_key(origin, p) for p in key.expected_pages}
    visited_keys = [row["effective_key"] for row in full["pages"]]
    found = expected & set(visited_keys)
    recall = len(found) / len(expected) if expected else 1.0

    wrong_rows = [row["effective"] for row in full["pages"] if row["effective_key"] not in expected]
    repeats = len(visited_keys) - len(set(visited_keys))
    must_not = {p for case in key.hard_cases for p in case.must_not_request}
    forbidden_requests = [path for _t, path in full_requests if _path_only(path) in must_not]
    wrong_pages = len(wrong_rows) + repeats + len(forbidden_requests)

    page_requests = [(t, p) for t, p in full_requests if _is_page_request(p)]
    other_requests = [p for _t, p in full_requests if not _is_page_request(p)]
    unique_found = len(set(visited_keys))
    fetches_per_page = len(page_requests) / unique_found if unique_found else float("inf")
    seconds_to_90 = _seconds_to_recall(page_requests, key, 0.9)

    cases = [_score_case(case, origin, full, full_requests) for case in key.hard_cases]
    honesty = _score_honesty(key, origin_d, default, capped, config.capped_max_pages)

    failures: list[str] = []
    if recall < config.min_recall:
        failures.append(f"recall {recall:.1%} is below {config.min_recall:.0%}")
    if wrong_pages > config.max_wrong_pages:
        failures.append(f"{wrong_pages} wrong pages (allowed {config.max_wrong_pages})")
    if fetches_per_page > config.max_fetches_per_page:
        failures.append(
            f"{fetches_per_page:.3f} page fetches per unique page "
            f"(allowed {config.max_fetches_per_page})"
        )
    failures.extend(f"hard case {c['id']}: {problem}" for c in cases for problem in c["problems"])
    failures.extend(f"honesty: {problem}" for problem in honesty["problems"])

    return {
        "status": "pass" if not failures else "fail",
        "site": str(config.site_dir),
        "start_path": key.start_path,
        "thresholds": {
            "min_recall": config.min_recall,
            "max_wrong_pages": config.max_wrong_pages,
            "max_fetches_per_page": config.max_fetches_per_page,
        },
        "recall": recall,
        "expected_pages": len(expected),
        "pages_found": len(found),
        "missed_pages": sorted(_path_of(p) for p in expected - found),
        "wrong_pages": wrong_pages,
        "wrong_page_rows": sorted(wrong_rows),
        "repeated_page_rows": repeats,
        "forbidden_requests": forbidden_requests,
        "efficiency": {
            "page_requests": len(page_requests),
            "unique_pages_found": unique_found,
            "fetches_per_page": fetches_per_page,
            "seconds_to_90_percent_recall": seconds_to_90,
            "other_requests": sorted(other_requests),
            "extra_page_requests": _extra_requests(page_requests, full),
        },
        "full_run": _run_summary(full),
        "hard_cases": cases,
        "honesty": honesty,
        "failures": failures,
    }


def format_coverage_markdown(report: dict[str, Any]) -> list[str]:
    """The crawl-coverage section of the detection-eval Markdown report."""
    eff = report["efficiency"]
    honesty = report["honesty"]
    lines = [
        "## Crawl coverage",
        "",
        (
            "The real crawler scans the test site in `tests/fixtures/site/coverage` "
            "from `/docs/` and is scored against the site's answer key, "
            "`expected.json`. Plain-HTTP crawl, no browser."
        ),
        "",
        f"Result: **{str(report['status']).upper()}**",
        "",
        "| Score | Result | Pass mark |",
        "| --- | ---: | ---: |",
        (
            f"| Recall (expected pages visited) | {report['pages_found']} of "
            f"{report['expected_pages']} ({report['recall']:.0%}) | "
            f"{report['thresholds']['min_recall']:.0%} |"
        ),
        (
            f"| Wrong pages (out of scope, blocked, repeated) | {report['wrong_pages']} | "
            f"at most {report['thresholds']['max_wrong_pages']} |"
        ),
        (
            f"| Page fetches per unique page | {eff['page_requests']} / "
            f"{eff['unique_pages_found']} = {eff['fetches_per_page']:.3f} | "
            f"{report['thresholds']['max_fetches_per_page']} or lower |"
        ),
        f"| Seconds to 90% recall | {eff['seconds_to_90_percent_recall']} | not gated |",
        "",
        "### Hard cases",
        "",
        "| Case | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for case in report["hard_cases"]:
        detail = "; ".join(case["problems"]) or "; ".join(case["evidence"])
        lines.append(f"| {case['label']} | {'pass' if case['passed'] else 'FAIL'} | {detail} |")
    lines.extend(
        [
            "",
            "### Honesty: pages the report says it did not visit",
            "",
            "| Run | Page limit | Depth limit | Blocked |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name in ("default_limits", "page_capped"):
        run = honesty[name]
        lines.append(
            f"| {run['label']} | {run['unvisited_page_limit']} | "
            f"{run['unvisited_depth_limit']} | {run['unvisited_blocked']} |"
        )
    lines.extend(["", *(f"- {item}" for item in honesty["evidence"]), ""])
    if eff["extra_page_requests"]:
        lines.extend(
            [
                "Page requests beyond one per page:",
                "",
                *(f"- `{item}`" for item in eff["extra_page_requests"]),
                "",
            ]
        )
    return lines


# --- crawling -----------------------------------------------------------------


def _crawl(origin: str, key: AnswerKey, *, max_depth: int, max_pages: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="axcess-coverage-eval-") as tmp:
        conn = connect(Path(tmp) / "audit.db")
        try:
            for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
                if not path.name.endswith(".rollback.sql"):
                    conn.executescript(path.read_text(encoding="utf-8"))
            config = CrawlConfig(
                seed_url=origin + key.start_path,
                max_pages=max_pages,
                max_depth=max_depth,
                rps=500.0,
                workers=2,
                js_enabled=False,
                js_eager=False,
                image_extraction_enabled=False,
                ocr_enabled=False,
                vlm_enabled=False,
                semantic_enabled=False,
                axe_enabled=False,
                keyboard_probe_enabled=False,
                responsive_checks_enabled=False,
                focus_checks_enabled=False,
                visual_checks_enabled=False,
                interaction_checks_enabled=False,
                synthesize_enabled=False,
                capture_screenshots=False,
                store_rendered_html=False,
                resumable=False,
            )
            summary: CrawlSummary = asyncio.run(run_crawl(conn, config))
            scan = conn.execute(
                "SELECT status, unvisited_page_limit, unvisited_depth_limit, unvisited_blocked "
                "FROM scans WHERE id = ?",
                (summary.scan_id,),
            ).fetchone()
            pages = [
                {
                    "requested": row["url_normalized"],
                    "effective": row["final_url"] or row["url_normalized"],
                    "effective_key": _page_key(origin, row["final_url"] or row["url_normalized"]),
                    "status": row["status_code"],
                    "found_only_in_sitemap": bool(row["found_only_in_sitemap"]),
                }
                for row in conn.execute(
                    "SELECT url_normalized, final_url, status_code, found_only_in_sitemap "
                    "FROM pages WHERE scan_id = ? ORDER BY id",
                    (summary.scan_id,),
                )
            ]
            known_unvisited = [
                {"url": row["url_normalized"], "min_depth": row["min_depth"]}
                for row in conn.execute(
                    "SELECT url_normalized, min_depth FROM crawl_known_urls "
                    "WHERE scan_id = ? AND outcome IS NULL",
                    (summary.scan_id,),
                )
            ]
            known_all = [
                row["url_normalized"]
                for row in conn.execute(
                    "SELECT url_normalized FROM crawl_known_urls WHERE scan_id = ?",
                    (summary.scan_id,),
                )
            ]
            blocked = [
                row["url_normalized"]
                for row in conn.execute(
                    "SELECT url_normalized FROM crawl_known_urls "
                    "WHERE scan_id = ? AND outcome = 'blocked'",
                    (summary.scan_id,),
                )
            ]
        finally:
            conn.close()
    return {
        "max_depth": max_depth,
        "max_pages": max_pages,
        "status": scan["status"],
        "pages_fetched": summary.pages_fetched,
        "pages_duplicate": summary.pages_duplicate,
        "pages_from_sitemap": summary.pages_from_sitemap,
        "unvisited_page_limit": scan["unvisited_page_limit"],
        "unvisited_depth_limit": scan["unvisited_depth_limit"],
        "unvisited_blocked": scan["unvisited_blocked"],
        "pages": pages,
        "known_unvisited": known_unvisited,
        "known_all": known_all,
        "blocked": blocked,
    }


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: run[key]
        for key in (
            "max_depth",
            "max_pages",
            "status",
            "pages_fetched",
            "pages_duplicate",
            "pages_from_sitemap",
            "unvisited_page_limit",
            "unvisited_depth_limit",
            "unvisited_blocked",
        )
    }


# --- scoring ------------------------------------------------------------------


def _page_key(origin: str, url_or_path: str) -> str:
    """Compare pages by normalized address, ignoring letter case.

    The site ignores case, so ``/About.html`` and ``/about.html`` are one page;
    a crawl that records both has recorded the page twice.
    """
    url = url_or_path if "://" in url_or_path else origin + url_or_path
    return url_policy.normalize(url).casefold()


def _path_of(key: str) -> str:
    parts = urlsplit(key)
    return parts.path + (f"?{parts.query}" if parts.query else "")


def _path_only(raw_path: str) -> str:
    return urlsplit(raw_path).path.casefold()


def _is_page_request(raw_path: str) -> bool:
    path = urlsplit(raw_path).path
    last = path.rsplit("/", 1)[-1]
    return path.endswith("/") or last.endswith(".html") or "." not in last


def _seconds_to_recall(
    page_requests: list[tuple[float, str]], key: AnswerKey, share: float
) -> float | None:
    wanted = {p.split("?", 1)[0].casefold() for p in key.expected_pages}
    target = len(wanted) * share
    seen: set[str] = set()
    for seconds, raw in page_requests:
        path = urlsplit(raw).path.casefold()
        path = key.redirects.get(path, path)
        if path in wanted:
            seen.add(path)
            if len(seen) >= target:
                return round(seconds, 3)
    return None


def _extra_requests(page_requests: list[tuple[float, str]], run: dict[str, Any]) -> list[str]:
    """Requests that did not produce a new page row: duplicates and redirect hops."""
    counts: dict[str, int] = {}
    for _t, raw in page_requests:
        counts[raw] = counts.get(raw, 0) + 1
    recorded = {urlsplit(row["requested"]).path for row in run["pages"]}
    extra: list[str] = []
    for raw, count in sorted(counts.items()):
        if count > 1:
            extra.append(f"{raw} requested {count} times")
        elif urlsplit(raw).path not in recorded:
            extra.append(f"{raw} (no page row of its own: a redirect or duplicate)")
    return extra


def _score_case(
    case: HardCase, origin: str, run: dict[str, Any], requests: list[tuple[float, str]]
) -> dict[str, Any]:
    problems: list[str] = []
    evidence: list[str] = []
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in run["pages"]:
        rows_by_key.setdefault(row["effective_key"], []).append(row)
    for page in case.must_visit:
        if _page_key(origin, page) in rows_by_key:
            evidence.append(f"visited {page}")
        else:
            problems.append(f"did not visit {page}")
    for page in case.single_page_rows:
        rows = rows_by_key.get(_page_key(origin, page), [])
        if len(rows) > 1:
            problems.append(f"{page} recorded {len(rows)} times")
    for page in case.must_be_sitemap_only:
        rows = rows_by_key.get(_page_key(origin, page), [])
        if rows and all(row["found_only_in_sitemap"] for row in rows):
            evidence.append(f"{page} marked found only in a sitemap")
        else:
            problems.append(f"{page} is not marked as found only in a sitemap")
    requested_paths = [_path_only(raw) for _t, raw in requests]
    for page in case.must_not_request:
        hits = requested_paths.count(page.casefold())
        if hits:
            problems.append(f"requested {page} {hits} times")
        else:
            evidence.append(f"never requested {page}")
    for fragment in case.must_not_request_query:
        query_hits = [raw for _t, raw in requests if fragment in raw]
        if query_hits:
            problems.append(f"requested {query_hits}")
        else:
            evidence.append(f"never requested an address with {fragment}")
    for page in case.counts_as_blocked:
        if _page_key(origin, page) in {_page_key(origin, url) for url in run["blocked"]}:
            evidence.append(f"{page} counted as blocked")
        else:
            problems.append(f"{page} not counted as blocked")
    return {
        "id": case.id,
        "label": case.label,
        "passed": not problems,
        "problems": problems,
        "evidence": evidence,
    }


def _score_honesty(
    key: AnswerKey,
    origin: str,
    default: dict[str, Any],
    capped: dict[str, Any],
    cap: int,
) -> dict[str, Any]:
    problems: list[str] = []
    evidence: list[str] = []
    blocked_expected = {p for case in key.hard_cases for p in case.counts_as_blocked}
    deep = [p for case in key.hard_cases if case.id == "deep_page" for p in case.must_visit]

    # Default limits: the 11-step page is the only one past depth 10.
    if default["unvisited_depth_limit"] != len(deep):
        problems.append(
            f"default limits: depth-limit count {default['unvisited_depth_limit']}, "
            f"expected {len(deep)}"
        )
    deep_keys = {_page_key(origin, p) for p in deep}
    counted_deep = {_page_key(origin, row["url"]) for row in default["known_unvisited"]}
    if deep_keys != counted_deep:
        problems.append(f"default limits: unvisited pages {sorted(counted_deep)}")
    else:
        evidence.append(f"default limits: {', '.join(deep)} counted under the depth limit")
    if default["unvisited_blocked"] != len(blocked_expected):
        problems.append(
            f"default limits: blocked count {default['unvisited_blocked']}, "
            f"expected {len(blocked_expected)}"
        )
    else:
        evidence.append(
            f"default limits: {default['unvisited_blocked']} blocked "
            f"({', '.join(sorted(blocked_expected))})"
        )
    if default["unvisited_page_limit"] != 0:
        problems.append(
            f"default limits: page-limit count {default['unvisited_page_limit']}, expected 0"
        )

    # Page cap: stopped early, so the count must be positive and every page
    # it counts must be a real, expected page the crawl did not visit.
    capped_origin = urlsplit(capped["pages"][0]["requested"]) if capped["pages"] else None
    base = f"{capped_origin.scheme}://{capped_origin.netloc}" if capped_origin else origin
    capped_expected = {_page_key(base, p) for p in key.expected_pages}
    # A known address that redirects to an expected page is a real address the
    # crawl could not know was a redirect without visiting it.
    capped_expected |= {_page_key(base, p) for p in key.redirects}
    known_all = set(capped["known_all"])
    counted = [row["url"] for row in capped["known_unvisited"]]
    # The slash-less spelling of a known folder is the same page, counted once.
    twins = [u for u in counted if crawl_coverage.directory_twin(u) in known_all]
    counted = [u for u in counted if u not in twins]
    stray = [u for u in counted if _page_key(base, u) not in capped_expected]
    if capped["pages_fetched"] != cap:
        problems.append(f"page cap {cap}: visited {capped['pages_fetched']} pages")
    if not capped["unvisited_page_limit"]:
        problems.append(f"page cap {cap}: no pages counted under the page limit")
    if capped["unvisited_page_limit"] + capped["unvisited_depth_limit"] != len(counted):
        problems.append("page cap: stored counts do not match the known-page list")
    if stray:
        problems.append(f"page cap: counted pages that are not expected pages: {stray}")
    if not problems or capped["unvisited_page_limit"]:
        evidence.append(
            f"page cap {cap}: visited {capped['pages_fetched']}, counted "
            f"{capped['unvisited_page_limit']} under the page limit, all of them expected pages"
        )
    return {
        "problems": problems,
        "evidence": evidence,
        "default_limits": {
            "label": "Default limits (500 pages, depth 10)",
            **_run_summary(default),
        },
        "page_capped": {"label": f"Page limit {cap}", **_run_summary(capped)},
    }


# --- the test-site server -----------------------------------------------------


@contextmanager
def _serve(site_dir: Path, key: AnswerKey) -> Iterator[tuple[str, _RequestLog]]:
    log = _RequestLog()
    root = site_dir.resolve()
    redirects = {k.casefold(): v for k, v in key.redirects.items()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            log.add(self.path)
            path = urlsplit(self.path).path
            target = redirects.get(path.casefold())
            if target is not None:
                self._redirect(target)
                return
            resolved = _resolve(root, path)
            if resolved is None:
                self._send(404, b"not found", "text/plain")
                return
            if resolved.is_dir():
                if not path.endswith("/"):
                    self._redirect(path + "/")
                    return
                resolved = resolved / "index.html"
                if not resolved.is_file():
                    self._send(404, b"not found", "text/plain")
                    return
            body = resolved.read_bytes()
            if resolved.suffix in _TEMPLATED_SUFFIXES:
                origin = f"http://{self.headers.get('Host', '127.0.0.1')}"
                body = body.replace(b"{{ORIGIN}}", origin.encode())
            self._send(200, body, _CONTENT_TYPES.get(resolved.suffix, "application/octet-stream"))

        def _redirect(self, location: str) -> None:
            self.send_response(301)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", log
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _resolve(root: Path, path: str) -> Path | None:
    """Find ``path`` under ``root`` matching each part without regard to case."""
    current = root
    for part in [p for p in path.split("/") if p]:
        if part in (".", ".."):
            return None
        if not current.is_dir():
            return None
        match = next((c for c in current.iterdir() if c.name.casefold() == part.casefold()), None)
        if match is None:
            return None
        current = match
    return current
