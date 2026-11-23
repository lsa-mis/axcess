"""One ``check.not_run`` log line, with the reason, for every check that did not run."""

from __future__ import annotations

from structlog.testing import capture_logs

from audit import check_log


def test_a_check_that_did_not_run_says_where_and_why() -> None:
    with capture_logs() as logs:
        check_log.not_run(
            "alfa",
            scope="page",
            url="https://example.edu/",
            reason="Alfa took longer than 75 seconds to check this page state.",
        )

    assert logs == [
        {
            "event": "check.not_run",
            "log_level": "warning",
            "check": "alfa",
            "scope": "page",
            "url": "https://example.edu/",
            "reason": "Alfa took longer than 75 seconds to check this page state.",
        }
    ]


def test_a_check_the_person_turned_off_is_info() -> None:
    with capture_logs() as logs:
        check_log.not_run("ocr", scope="scan", reason="Turned off.", chosen=True)

    assert logs[0]["log_level"] == "info"


def test_a_sign_in_scan_line_has_no_address_and_no_copied_error_output() -> None:
    with capture_logs() as logs:
        check_log.not_run(
            "alfa",
            scope="page",
            url="https://app.example.edu/records/123",
            protected=True,
            reason="The Alfa worker stopped unexpectedly. Error output: GET /records/123 failed",
        )

    line = logs[0]
    assert "url" not in line
    assert line["protected_context"] is True
    assert line["reason"] == "The Alfa worker stopped unexpectedly."


def test_failure_gives_only_the_error_type_in_a_sign_in_scan() -> None:
    error = RuntimeError("navigated to https://app.example.edu/records/123")

    assert check_log.failure("Axe's check of the page", error) == (
        "Axe's check of the page failed "
        "(RuntimeError: navigated to https://app.example.edu/records/123)."
    )
    assert check_log.failure("Axe's check of the page", error, protected=True) == (
        "Axe's check of the page failed (RuntimeError)."
    )


def test_url_of_never_raises() -> None:
    class Broken:
        @property
        def url(self) -> str:
            raise RuntimeError("closed")

    assert check_log.url_of(Broken()) is None
    assert check_log.url_of(None) is None
