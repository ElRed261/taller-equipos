"""Application configuration.

All settings are read from the environment with the ``TALLER_`` prefix, and
from a local ``.env`` file when present. The database URL is never hardcoded in
importable modules: the Alembic environment and the UI both read it from here.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TALLER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="",
        description=(
            "SQLAlchemy URL for the workshop database. Resolution order: the "
            "TALLER_DATABASE_URL environment variable, the .env file, the "
            "configuration written by the first-run wizard, and finally a local "
            "default."
        ),
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def _desde_el_asistente(cls, valor: str) -> str:
        """Fall back to what the first-run wizard saved, if nothing else is set."""
        if valor:
            return valor
        from taller.arranque import cargar_configuracion

        guardada = cargar_configuracion().database_url
        return guardada or "postgresql+psycopg://taller@localhost:5432/taller"
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
