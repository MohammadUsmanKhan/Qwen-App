"""Settings, read from TOOLS_* environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOOLS_", extra="ignore")

    api_key: str = ""
    signing_key: str = "dev-signing-key"
    public_url: str = "http://localhost:8001"
    link_ttl_hours: int = 168

    data_dir: Path = Path("/data")
    owui_data_dir: Path = Path("/owui")
    # Open WebUI stores upload paths as seen inside its own container.
    owui_container_data_dir: str = "/app/backend/data"
    # Without the forwarded user header we can't tell whose uploads are whose,
    # so refuse instead of exposing every user's files.
    require_user_header: bool = True

    docling_url: str = "http://docling:5001"
    docling_timeout_s: float = 600
    llm_url: str = "http://llama:8080/v1"

    read_max_chars: int = 20_000
    max_upload_mb: int = 200
    soffice_bin: str = "soffice"
    render_timeout_s: float = 180

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
