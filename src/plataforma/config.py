from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PLATAFORMA_", extra="ignore")

    database_url: str = "postgresql+psycopg://plataforma:plataforma@localhost:5432/plataforma"
    sources_dir: Path = Path("sources")
    origen_batch_size: int = 2000
    http_user_agent: str = "plataforma-datos/0.1"
    # Claves de la API separadas por coma. Vacío = API abierta (solo para desarrollo local).
    api_keys: str = ""
    # Orígenes web autorizados a llamar la API desde un navegador, separados por coma.
    cors_origins: str = ""
    # Conexión del servidor MCP; conviene un usuario creado con `plataforma crear-lector`.
    mcp_database_url: str | None = None


def split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
