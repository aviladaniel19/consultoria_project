from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PLATAFORMA_", extra="ignore")

    database_url: str = "postgresql+psycopg://plataforma:plataforma@localhost:5432/plataforma"
    sources_dir: Path = Path("sources")
    origen_batch_size: int = 2000
    http_user_agent: str = "plataforma-datos/0.1"
    # Carpeta donde la plataforma web guarda los archivos que se suben
    landing_dir: Path = Path("data/landing")
    max_subida_mb: int = 200
    # Permite conectar desde la web APIs en redes privadas (p. ej. servicios internos de la
    # universidad). Por defecto solo APIs públicas, para que nadie apunte a la red interna.
    permitir_redes_privadas: bool = False
    # Filas que el motor de calidad MinTIC lee de la tabla publicada; por encima, una muestra aleatoria.
    calidad_max_filas: int = 200_000
    # Claves de la API separadas por coma. Vacío = API abierta (solo para desarrollo local).
    api_keys: str = ""
    # Claves que además permiten cargar, actualizar y eliminar fuentes desde la web.
    # Sin ninguna clave configurada (uso local), cualquiera puede administrar.
    admin_keys: str = ""
    # Orígenes web autorizados a llamar la API desde un navegador, separados por coma.
    cors_origins: str = ""
    # Conexión del servidor MCP; conviene un usuario creado con `plataforma crear-lector`.
    mcp_database_url: str | None = None


def split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def claves_acceso() -> list[str]:
    """Claves que permiten consultar: las de lectura y las de administración."""
    s = get_settings()
    return split_csv(s.api_keys) + split_csv(s.admin_keys)


@lru_cache
def get_settings() -> Settings:
    return Settings()
