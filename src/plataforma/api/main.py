"""API de servicio: expone el catálogo y los datasets de las capas estandarizada y analítica.

Es genérica: no conoce ninguna fuente en particular. Lo que existe se
descubre en `meta.*` y en `information_schema`, así que cada fuente o modelo
dbt nuevo aparece aquí sin tocar código.
"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from sqlalchemy import Connection, text

from .. import consultas
from ..config import get_settings, split_csv
from ..storage.db import bootstrap, get_engine
from ..web import instalar_frontend

log = logging.getLogger(__name__)
Layer = Literal["estandarizado", "analitico"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap(get_engine())
    if not split_csv(get_settings().api_keys):
        log.warning("PLATAFORMA_API_KEYS está vacío: la API queda abierta. Úsalo solo en desarrollo local.")
    yield


app = FastAPI(
    title="Plataforma de datos",
    version="0.1.0",
    description="Catálogo de fuentes, ejecuciones, calidad y datasets modelados. "
                "Todos los endpoints salvo /health piden la cabecera X-API-Key.",
    lifespan=lifespan,
)
if origins := split_csv(get_settings().cors_origins):
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                       allow_headers=["X-API-Key"])

_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_key(key: str | None = Security(_api_key)) -> None:
    """Exige una de las claves de PLATAFORMA_API_KEYS. Sin claves configuradas, no exige nada."""
    keys = split_csv(get_settings().api_keys)
    if not keys:
        return
    if not key or not any(secrets.compare_digest(key, k) for k in keys):
        raise HTTPException(401, "falta la cabecera X-API-Key o la clave no es válida",
                            headers={"WWW-Authenticate": "APIKey"})


router = APIRouter(dependencies=[Depends(require_key)])


def db():
    with get_engine().connect() as conn:
        yield conn


def rows(result) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in result]


# ---------------------------------------------------------------------- salud
@app.get("/health", tags=["sistema"])
def health(conn: Connection = Depends(db)) -> dict[str, str]:
    conn.execute(text("SELECT 1"))
    return {"status": "ok"}


# -------------------------------------------------------------------- catálogo
@router.get("/sources", tags=["catálogo"])
def list_sources(tag: str | None = None, conn: Connection = Depends(db)) -> list[dict[str, Any]]:
    q = text("""
        SELECT s.name, s.description, s.owner, s.tags, s.type, s.enabled, s.updated_at,
               st.cursor_value, st.updated_at AS cursor_updated_at,
               r.status AS last_status, r.finished_at AS last_run_at, r.records_loaded AS last_records,
               (SELECT max(version) FROM meta.schema_versions v WHERE v.source_name = s.name) AS schema_version
        FROM meta.sources s
        LEFT JOIN meta.state st ON st.source_name = s.name
        LEFT JOIN LATERAL (
            SELECT status, finished_at, records_loaded FROM meta.runs
            WHERE source_name = s.name ORDER BY started_at DESC LIMIT 1
        ) r ON true
        WHERE (CAST(:tag AS text) IS NULL OR CAST(:tag AS text) = ANY(s.tags))
        ORDER BY s.name
    """)
    return rows(conn.execute(q, {"tag": tag}))


@router.get("/sources/{name}", tags=["catálogo"])
def source_detail(name: str, conn: Connection = Depends(db)) -> dict[str, Any]:
    src = conn.execute(text("SELECT * FROM meta.sources WHERE name = :n"), {"n": name}).first()
    if not src:
        raise HTTPException(404, f"fuente '{name}' no registrada")
    schema = conn.execute(text("""
        SELECT version, columns, added, retyped, detected_at FROM meta.schema_versions
        WHERE source_name = :n ORDER BY version DESC LIMIT 1
    """), {"n": name}).first()
    profiles = conn.execute(text("""
        SELECT p.* FROM meta.column_profiles p
        WHERE p.run_id = (SELECT run_id FROM meta.runs WHERE source_name = :n AND records_loaded > 0
                          ORDER BY started_at DESC LIMIT 1)
        ORDER BY p.column_name
    """), {"n": name})
    return {
        "source": dict(src._mapping),
        "schema": dict(schema._mapping) if schema else None,
        "last_profile": rows(profiles),
    }


@router.get("/sources/{name}/schema-history", tags=["catálogo"])
def schema_history(name: str, conn: Connection = Depends(db)) -> list[dict[str, Any]]:
    return rows(conn.execute(text("""
        SELECT version, added, retyped, detected_at, run_id FROM meta.schema_versions
        WHERE source_name = :n ORDER BY version
    """), {"n": name}))


@router.get("/sources/{name}/runs", tags=["ejecuciones"])
def source_runs(name: str, limit: int = Query(20, ge=1, le=200), conn: Connection = Depends(db)):
    return rows(conn.execute(text("""
        SELECT * FROM meta.runs WHERE source_name = :n ORDER BY started_at DESC LIMIT :l
    """), {"n": name, "l": limit}))


@router.get("/sources/{name}/profile-history/{column}", tags=["calidad"])
def profile_history(name: str, column: str, conn: Connection = Depends(db)):
    """Serie del perfil de una columna a lo largo de las cargas: insumo para detectar derivas."""
    return rows(conn.execute(text("""
        SELECT r.started_at, p.n, p.null_rate, p.n_distinct, p.mean, p.std, p.p50, p.min_value, p.max_value
        FROM meta.column_profiles p JOIN meta.runs r USING (run_id)
        WHERE p.source_name = :n AND p.column_name = :c ORDER BY r.started_at
    """), {"n": name, "c": column}))


@router.get("/runs/{run_id}/quality", tags=["calidad"])
def run_quality(run_id: UUID, conn: Connection = Depends(db)):
    return rows(conn.execute(text(
        "SELECT * FROM meta.quality_results WHERE run_id = :r ORDER BY passed, column_name"
    ), {"r": run_id}))


# --------------------------------------------------------------------- datasets
FILTRO_AYUDA = ("Repetible. Formato columna:operador:valor, con operador entre "
                + ", ".join(consultas.OPERADORES) + ". Ej.: departamento:eq:Antioquia")


def _filtros(filtro: list[str]) -> list[consultas.Filtro]:
    try:
        return [consultas.Filtro.desde_texto(f) for f in filtro]
    except consultas.ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from None


@router.get("/datasets", tags=["datasets"])
def list_datasets(layer: Layer | None = None, conn: Connection = Depends(db)):
    return consultas.tablas(conn, layer)


@router.get("/datasets/{layer}/{name}", tags=["datasets"])
def read_dataset(
    layer: Layer,
    name: str,
    limit: int = Query(100, ge=1, le=10_000),
    offset: int = Query(0, ge=0),
    order_by: str | None = Query(None, description="Columna; prefijo '-' para descendente"),
    filtro: list[str] = Query([], description=FILTRO_AYUDA),
    conn: Connection = Depends(db),
):
    try:
        return consultas.leer_tabla(conn, layer, name, _filtros(filtro), order_by, limit, offset)
    except consultas.TablaNoExiste as e:
        raise HTTPException(404, str(e)) from None
    except consultas.ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from None


@router.get("/datasets/{layer}/{name}/csv", tags=["datasets"])
def download_dataset(
    layer: Layer,
    name: str,
    order_by: str | None = Query(None, description="Columna; prefijo '-' para descendente"),
    filtro: list[str] = Query([], description=FILTRO_AYUDA),
    sep: Literal[",", ";"] = Query(",", description="';' para Excel con configuración regional de Colombia"),
    conn: Connection = Depends(db),
):
    """Descarga el dataset completo (o filtrado) en CSV UTF-8."""
    try:
        sql, params, encabezado = consultas.preparar_exportacion(conn, layer, name, _filtros(filtro), order_by)
    except consultas.TablaNoExiste as e:
        raise HTTPException(404, str(e)) from None
    except consultas.ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from None
    return StreamingResponse(
        consultas.transmitir_csv(conn.engine, sql, params, encabezado, sep),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{layer}_{name}.csv"'},
    )


app.include_router(router)
instalar_frontend(app)
