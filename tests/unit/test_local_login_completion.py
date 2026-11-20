"""Truthful completion states for direct local login scans."""

from pathlib import Path

import pytest

from audit.ai.model_client import ModelEndpoint
from audit.config import Settings
from audit.crawler.orchestrator import CrawlSummary
from audit.web.server import (
    _estimate_scan_eta,
    _local_login_completion,
    _local_login_model_endpoint,
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


def test_local_login_model_accepts_the_llama_cpp_socket(tmp_path: Path) -> None:
    """A UNIX socket is a file on this computer, so it is local by construction."""
    sock = tmp_path / "ai" / "scratch" / "llama.sock"
    settings = Settings(
        data_dir=tmp_path,
        model_backend="llama_cpp",
        llama_cpp_url="http://localhost",
        llama_cpp_socket=sock,
    )
    assert _local_login_model_endpoint(settings) == ModelEndpoint(
        "llama_cpp", "http://localhost", str(sock)
    )


@pytest.mark.parametrize(
    ("backend", "url", "expected"),
    [
        ("ollama", "http://localhost:11434", "http://127.0.0.1:11434"),
        ("ollama", "http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("llama_cpp", "http://localhost:8080", "http://127.0.0.1:8080"),
        ("ollama", "https://ollama.example.test", None),
        ("ollama", "http://192.168.1.20:11434", None),
        ("llama_cpp", "http://192.168.1.20:8080", None),
        ("llama_cpp", "http://127.0.0.1:8080/?token=secret", None),
    ],
)
def test_local_login_model_over_tcp_needs_literal_loopback(
    tmp_path: Path, backend: str, url: str, expected: str | None
) -> None:
    field = "llama_cpp_url" if backend == "llama_cpp" else "ollama_base_url"
    settings = Settings(data_dir=tmp_path, model_backend=backend, **{field: url})
    endpoint = _local_login_model_endpoint(settings)
    if expected is None:
        assert endpoint is None
    else:
        assert endpoint == ModelEndpoint(backend, expected)
        assert endpoint.socket_path is None


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


def test_scan_readiness_reasons_name_the_service_in_use(tmp_path) -> None:
    from audit.config import Settings
    from audit.web.server import _model_missing_reason, _service_down_reason

    desktop = Settings(data_dir=tmp_path, desktop=True)
    assert "private AI service" in _service_down_reason(desktop)
    assert "Settings → AI features" in _model_missing_reason(desktop, ["m"])
    assert "Ollama" not in _service_down_reason(desktop) + _model_missing_reason(desktop, ["m"])

    own_ollama = Settings(data_dir=tmp_path)
    assert _service_down_reason(own_ollama) == "Ollama is not running on this computer."
    assert (
        _model_missing_reason(own_ollama, ["m:1"])
        == "Install the local model with: ollama pull m:1"
    )

    llama = Settings(data_dir=tmp_path, model_backend="llama_cpp")
    assert "Ollama" not in _service_down_reason(llama) + _model_missing_reason(llama, ["m"])
