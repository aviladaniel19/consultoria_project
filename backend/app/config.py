"""
config.py — Configuración centralizada con BaseSettings.

Patrón del curso Python para APIs e IA (Semana 6):
  - BaseSettings lee variables de entorno y del archivo .env automáticamente.
  - NUNCA se hardcodean API keys en el código fuente.
  - Todas las variables están documentadas en .env.example
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os


class Settings(BaseSettings):
    """
    Configuración de la aplicación.

    Pydantic-settings carga automáticamente desde:
      1. Variables de entorno del sistema operativo
      2. Archivo .env (si existe)

    El orden de prioridad es: variable de entorno > .env > valor por defecto.
    """

    model_config = SettingsConfigDict(
        # Busca .env en backend/ (local) o en la raíz del proyecto (Docker)
        env_file=[
            os.path.join(os.path.dirname(__file__), "..", ".env"),   # backend/.env
            os.path.join(os.path.dirname(__file__), "..", "..", ".env"),  # vigia/.env
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── APIs y LLM Providers ───────────────────────────────
    GROQ_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""

    # ── Parámetros de Auth ────────────────────────────────
    SECRET_KEY: str = "clave_secreta_vigia_desarrollo_cambiar_en_produccion"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # ── Base de Datos ─────────────────────────────────────
    # SQLite para desarrollo local; PostgreSQL en Docker (override con .env)
    DATABASE_URL: str = "sqlite:///./vigia_dev.db"

    # ── Servidor ──────────────────────────────────────────
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # ── CORS ──────────────────────────────────────────────
    # En producción, restringir a la URL del frontend
    CORS_ORIGINS: list[str] = ["*"]


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna una instancia cacheada de Settings.

    lru_cache garantiza que Settings() se instancie UNA SOLA VEZ
    durante el ciclo de vida de la aplicación. Esto es eficiente porque
    BaseSettings lee archivos de disco en cada instanciación.

    Uso con FastAPI Depends():
        @app.get("/ejemplo")
        async def endpoint(cfg: Settings = Depends(get_settings)):
            ...
    """
    return Settings()
