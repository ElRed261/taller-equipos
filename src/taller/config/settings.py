"""Application configuration.

All settings are read from the environment with the ``TALLER_`` prefix, and
from a local ``.env`` file when present. The database URL is never hardcoded in
importable modules: the Alembic environment and the UI both read it from here.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TALLER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://taller@localhost:5432/taller",
        description="SQLAlchemy URL for the workshop database.",
    )
    pool_size: int = Field(default=5, ge=1, le=50)
    pool_max_overflow: int = Field(default=5, ge=0, le=50)
    search_debounce_ms: int = Field(default=250, ge=0, le=2000)
    usuario: str = Field(
        default="",
        description=(
            "Nombre del usuario de la aplicación, usado para atribuir cada edición. "
            "Nunca se toma del sistema operativo: la auditoría registra quién dice la "
            "app que actuó, no el dueño del proceso."
        ),
    )

    @property
    def sqlalchemy_psycopg_url(self) -> str:
        """URL as stored, for diagnostics without credentials."""
        head, _, _ = self.database_url.partition("@")
        return head.split("://")[0] + "://***" + ("@" if head.count("@") else "")


def get_settings() -> Settings:
    return Settings()
