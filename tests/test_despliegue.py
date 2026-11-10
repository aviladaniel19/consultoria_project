"""Configuración para despliegue: URL de la base de datos y arranque sin base de datos."""
import logging

import pytest
from sqlalchemy import make_url

from plataforma.api import main
from plataforma.config import Settings, url_postgres


@pytest.mark.parametrize("entrada,esperada", [
    ("postgres://u:p@dpg-abc-a/plataforma", "postgresql+psycopg://u:p@dpg-abc-a/plataforma"),
    ("postgresql://u:p@dpg-abc-a:5432/plataforma", "postgresql+psycopg://u:p@dpg-abc-a:5432/plataforma"),
    ("postgresql+psycopg://u:p@db:5432/plataforma", "postgresql+psycopg://u:p@db:5432/plataforma"),
    (None, None),
])
def test_la_url_de_render_usa_psycopg_3(entrada, esperada):
    assert url_postgres(entrada) == esperada
    # SQLAlchemy la resuelve al driver correcto, no a psycopg2
    if esperada:
        assert make_url(url_postgres(entrada)).get_driver_name() == "psycopg"


def test_settings_normaliza_la_url_que_viene_del_entorno(monkeypatch):
    monkeypatch.setenv("PLATAFORMA_DATABASE_URL", "postgres://u:p@dpg-abc-a/plataforma?sslmode=require")
    monkeypatch.setenv("PLATAFORMA_MCP_DATABASE_URL", "postgresql://lector:p@dpg-abc-a/plataforma")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://u:p@dpg-abc-a/plataforma?sslmode=require"
    assert s.mcp_database_url == "postgresql+psycopg://lector:p@dpg-abc-a/plataforma"


def test_el_arranque_sin_base_de_datos_dice_que_falta_la_variable(monkeypatch, caplog):
    import asyncio

    from sqlalchemy import create_engine

    monkeypatch.delenv("PLATAFORMA_DATABASE_URL", raising=False)
    # un puerto cerrado en localhost: la misma situación que el despliegue sin variable
    monkeypatch.setattr(main, "get_engine", lambda: create_engine(
        "postgresql+psycopg://u:p@127.0.0.1:1/plataforma", connect_args={"connect_timeout": 2}))
    monkeypatch.setattr(main.get_settings(), "database_url", "postgresql+psycopg://u:clave-secreta@localhost:5432/x")
    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as salida:
        asyncio.run(main.lifespan(main.app).__aenter__())
    assert salida.value.code == 3
    mensaje = caplog.text
    assert "PLATAFORMA_DATABASE_URL no está definida" in mensaje and "localhost:5432" in mensaje
    assert "clave-secreta" not in mensaje                      # nunca se imprime la contraseña
