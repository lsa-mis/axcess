"""Truthful completion states for direct local login scans."""

from audit.crawler.orchestrator import CrawlSummary
from audit.web.server import (
    _estimate_scan_eta,
    _local_login_completion,
    _local_login_ollama_url,
)


def test_login_scan_with_no_captured_pages_is_not_reported_complete() -> None:
    summary = CrawlSummary(
        scan_id=7,
        seed_url="https://app.example.test/secure/",
        pages_fetched=0,
        errors=3,
        status="completed",
    )

    status, error = _local_login_completion(summary)

    assert status == "failed"
    assert error is not None
    assert "Sign-in succeeded" in error


def test_login_scan_with_captured_pages_preserves_completed_state() -> None:
    summary = CrawlSummary(
        scan_id=8,
        seed_url="https://app.example.test/secure/",
        pages_fetched=2,
        status="completed",
    )

    assert _local_login_completion(summary) == ("completed", None)


def test_local_login_ollama_normalizes_localhost_to_literal_loopback() -> None:
    assert _local_login_ollama_url("http://localhost:11434") == "http://127.0.0.1:11434"
    assert _local_login_ollama_url("http://127.0.0.1:11434") == ("http://127.0.0.1:11434")


def test_local_login_ollama_rejects_non_loopback_or_secret_bearing_urls() -> None:
    assert _local_login_ollama_url("https://ollama.example.test") is None
    assert _local_login_ollama_url("http://127.0.0.1:11434?token=secret") is None
    assert _local_login_ollama_url("http://user:pass@127.0.0.1:11434") is None


def test_scan_eta_waits_for_observed_page_pace() -> None:
    assert _estimate_scan_eta(
        stage="scanning",
        completed=1,
        failed=0,
        pending=4,
        leased=1,
        observed_seconds=8,
    ) == {
        "state": "estimating",
        "min_seconds": None,
        "max_seconds": None,
        "based_on_pages": 1,
    }


def test_scan_eta_is_a_conservative_range_for_known_remaining_pages() -> None:
    eta = _estimate_scan_eta(
        stage="scanning",
        completed=4,
        failed=0,
        pending=2,
        leased=1,
        observed_seconds=30,
    )

    assert eta == {
        "state": "range",
        "min_seconds": 20,
        "max_seconds": 68,
        "based_on_pages": 4,
    }


def test_scan_eta_labels_report_finalization_separately() -> None:
    assert _estimate_scan_eta(
        stage="preparing_report",
        completed=10,
        failed=0,
        pending=0,
        leased=0,
        observed_seconds=90,
    ) == {
        "state": "finalizing",
        "min_seconds": 5,
        "max_seconds": 30,
        "based_on_pages": 10,
    }
