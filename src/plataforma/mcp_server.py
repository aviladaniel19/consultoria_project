"""Servidor MCP de solo lectura: permite que asistentes como Claude consulten la plataforma.

    plataforma-mcp            # transporte stdio (Claude Desktop, Claude Code)

Usa PLATAFORMA_MCP_DATABASE_URL, idealmente un usuario creado con `plataforma crear-lector`;
si no está definida, cae en la conexión principal. Cada llamada corre en una transacción de
solo lectura con límite de tiempo, así que ninguna herramienta puede modificar datos.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Callable
from typing import Any

import psycopg
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

from . import consultas
from .api import main as api
from .config import get_settings
from .storage.db import get_engine

log = logging.getLogger(__name__)
MAX_FILAS = 500
CAPAS = consultas.CAPAS
LECTURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)

server = MCPServer(
    name="plataforma-datos",
    instructions=(
        "Plataforma de datos con tres capas: origen (crudo, no accesible aquí), estandarizado "
        "(depurado y sin duplicados) y analitico (agregado para reportes). El esquema meta guarda el "
        "catálogo: fuentes, ejecuciones, calidad y perfiles por columna. Para responder preguntas sobre "
        "los datos: usa listar_datasets, luego describir_dataset para ver las columnas, y después "
        "consulta_sql con una sola consulta SELECT. Indica siempre de qué tabla sale cada cifra."
    ),
)


def _ejecutar(fn: Callable[[Connection], Any]) -> str:
    """Corre `fn` en una transacción de solo lectura y devuelve JSON, o un error legible para el modelo."""
    settings = get_settings()
    engine = get_engine(settings.mcp_database_url or settings.database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SET LOCAL statement_timeout = '30s'"))
            resultado = fn(conn)
    except HTTPException as e:
        resultado = {"error": e.detail}
    except (ValueError, LookupError, psycopg.Error) as e:
        resultado = {"error": str(e).strip()}
    except DBAPIError as e:
        resultado = {"error": str(e.orig).strip()}
    return json.dumps(jsonable_encoder(resultado), ensure_ascii=False, default=str)


def _capa(capa: str) -> str:
    if capa not in CAPAS:
        raise ValueError(f"capa desconocida: {capa}. Usa 'estandarizado' o 'analitico'")
    return capa


def _consulta(conn: Connection, sql: str) -> dict[str, Any]:
    q = sql.strip().rstrip(";").strip()
    if ";" in q:
        raise ValueError("solo se permite una consulta, sin ';' intermedios")
    if not re.match(r"(?is)^(select|with)\b", q):
        raise ValueError("solo se permiten consultas SELECT o WITH")
    conn.execute(text("SET LOCAL search_path = analitico, estandarizado, meta"))
    # cursor del driver sin parámetros: el texto del usuario no pasa por el procesado de marcadores,
    # así que '%' (LIKE) y '::' (conversiones) funcionan tal cual
    cur = conn.connection.driver_connection.cursor()
    cur.execute(f"SELECT * FROM (\n{q}\n) AS consulta LIMIT {MAX_FILAS + 1}")
    columnas = [d.name for d in cur.description]
    filas = cur.fetchall()
    return {
        "columnas": columnas,
        "filas": [dict(zip(columnas, f, strict=True)) for f in filas[:MAX_FILAS]],
        "truncado": len(filas) > MAX_FILAS,
    }


# ---------------------------------------------------------------------- herramientas
@server.tool(annotations=LECTURA)
def listar_fuentes(etiqueta: str | None = None) -> str:
    """Lista las fuentes registradas con su último estado de carga, cursor y versión de esquema.
    Opcionalmente filtra por etiqueta (por ejemplo 'contratacion')."""
    return _ejecutar(lambda c: api.list_sources(tag=etiqueta, conn=c))


@server.tool(annotations=LECTURA)
def describir_fuente(nombre: str) -> str:
    """Configuración (sin secretos), esquema vigente y perfil estadístico de la última carga de una fuente."""
    return _ejecutar(lambda c: api.source_detail(name=nombre, conn=c))


@server.tool(annotations=LECTURA)
def listar_datasets(capa: str | None = None) -> str:
    """Tablas disponibles en las capas 'estandarizado' y 'analitico'."""
    return _ejecutar(lambda c: consultas.tablas(c, _capa(capa) if capa else None))


@server.tool(annotations=LECTURA)
def describir_dataset(capa: str, nombre: str) -> str:
    """Columnas, tipos y descripción de una tabla, para escribir consultas correctas."""
    def fn(c: Connection) -> Any:
        cols = consultas.columnas(c, _capa(capa), nombre)
        if not cols:
            raise ValueError(f"el dataset {capa}.{nombre} no existe")
        return {"capa": capa, "nombre": nombre, "columnas": cols}
    return _ejecutar(fn)


@server.tool(annotations=LECTURA)
def consultar_dataset(capa: str, nombre: str, limite: int = 100, desplazamiento: int = 0,
                      ordenar_por: str | None = None) -> str:
    """Filas de una tabla, paginadas. `ordenar_por` es una columna; con prefijo '-' ordena descendente."""
    return _ejecutar(lambda c: consultas.leer_tabla(
        c, _capa(capa), nombre, orden=ordenar_por, limite=max(1, min(limite, MAX_FILAS)),
        desplazamiento=max(0, desplazamiento)))


@server.tool(annotations=LECTURA)
def consulta_sql(sql: str) -> str:
    """Ejecuta una consulta SELECT (o WITH) de solo lectura sobre las capas estandarizado y analitico y el
    catálogo meta, y devuelve hasta 500 filas. Úsala para sumas, conteos, filtros y agrupaciones.
    Ejemplo: SELECT departamento, sum(precio_base_total) FROM analitico.contratacion_mensual GROUP BY 1."""
    return _ejecutar(lambda c: _consulta(c, sql))


def main() -> None:
    # stdout es el canal del protocolo MCP: los avisos van a stderr
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    if not get_settings().mcp_database_url:
        log.warning("PLATAFORMA_MCP_DATABASE_URL no está definida: se usa la conexión principal. "
                    "Crea un usuario con `plataforma crear-lector` y úsalo aquí.")
    server.run("stdio")


if __name__ == "__main__":
    main()
