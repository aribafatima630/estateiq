from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-31b-it:free"
    openrouter_fallback_models: str = (
        "baidu/ernie-5.5-flash-preview:free,"
        "nvidia/nemotron-3.5-lightning:free,"
        "openrouter/free"
    )
    openrouter_site_url: str = "https://estateiq-pjt8.onrender.com"
    openrouter_app_name: str = "EstateIQ"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    admin_token: str = ""
    contact_email: str = ""
    data_dir: str = "./data"
    retrieval_threshold: float = 0.35
    retrieval_top_k: int = 6
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    scraper_enabled: bool = True
    auto_index_on_start: bool = False
    cors_origins: str = "https://estateiq-pjt8.onrender.com"
    host: str = "0.0.0.0"
    port: int = 8000

    wasalt_max_listings: int = 500
    wasalt_per_page: int = 16
    darglobal_max_pages: int = 90
    request_timeout_seconds: float = 30.0
    wasalt_delay_seconds: float = 1.25
    darglobal_delay_seconds: float = 2.0

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_data_dir(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def database_path(self) -> Path:
        return self.resolved_data_dir / "processed" / "estateiq.db"

    @property
    def index_path(self) -> Path:
        return self.resolved_data_dir / "indexes" / "estateiq.faiss"

    @property
    def index_meta_path(self) -> Path:
        return self.resolved_data_dir / "indexes" / "meta.json"

    @property
    def raw_dir(self) -> Path:
        return self.resolved_data_dir / "raw"

    @property
    def report_path(self) -> Path:
        return self.resolved_data_dir / "processed" / "ingestion_report.json"

    @property
    def fallback_model_list(self) -> list[str]:
        values = [self.openrouter_model, *self.openrouter_fallback_models.split(",")]
        seen: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in seen:
                seen.append(item)
        return seen

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def user_agent(self) -> str:
        contact = self.contact_email or "unset"
        return f"EstateIQ/1.0 (public-page research; contact: {contact})"


@lru_cache
def get_settings() -> Settings:
    return Settings()
