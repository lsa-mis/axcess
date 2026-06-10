"""Runtime configuration. Env vars (prefixed AUDIT_) or .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration resolved from env + defaults."""

    model_config = SettingsConfigDict(
        env_prefix="AUDIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"))
    db_path: Path = Field(default=Path("data/audit.db"))
    blob_dir: Path = Field(default=Path("data/blobs"))
    log_dir: Path = Field(default=Path("data/logs"))

    # Crawler
    default_rps: float = 2.0
    request_timeout_s: float = 30.0
    user_agent: str = "accessible-accessibility/0.1 (+local accessibility audit)"

    # OCR (Phase 3)
    ocr_language: str = "eng"
    ocr_max_workers: int = 2
    ocr_min_confidence: float = 60.0
    ocr_min_word_count: int = 3

    # VLM (Phase 4)
    ollama_base_url: str = "http://localhost:11434"
    vlm_model: str = "qwen2-vl:2b"
    vlm_concurrency: int = 1
    vlm_prompt_name: str = "classify_v1.txt"

    def ensure_dirs(self) -> None:
        """Create runtime directories if missing."""
        for p in (self.data_dir, self.blob_dir, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Build a fresh Settings instance (caller may cache)."""
    return Settings()
