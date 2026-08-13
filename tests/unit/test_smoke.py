"""Phase 0 smoke tests — confirm imports and CLI wiring."""

from __future__ import annotations

from typer.testing import CliRunner

import audit
from audit import cli
from audit.config import Settings


def test_package_version() -> None:
    assert audit.__version__ == "0.1.0"


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "crawl" in result.output
    assert "status" in result.output


def test_crawl_help_lists_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "--max-pages" in result.output
    assert "--ignore-robots" in result.output


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.vlm_model == "qwen3-vl:2b-instruct"
    assert settings.default_rps > 0
    assert settings.ocr_min_confidence > 0
