from functools import lru_cache
from importlib.resources import files

from sqlalchemy import Engine, create_engine, text

from ..config import get_settings


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url, pool_pre_ping=True, future=True)


def bootstrap(engine: Engine) -> None:
    """Crea esquemas y tablas del catálogo si no existen."""
    ddl = files("plataforma.storage").joinpath("ddl.sql").read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(ddl)


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def ensure_origen_table(engine: Engine, table: str) -> None:
    t = f"origen.{quote_ident(table)}"
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {t} (
                _id        bigserial PRIMARY KEY,
                _run_id    uuid NOT NULL,
                _loaded_at timestamptz NOT NULL DEFAULT now(),
                _record    jsonb NOT NULL
            )"""))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS {quote_ident(table + '_run_idx')} ON {t} (_run_id)"
        ))
