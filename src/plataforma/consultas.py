"""Consultas de lectura sobre las capas estandarizado y analitico.

Las comparten la API, el frontend y el servidor MCP. Nombres de tabla, columnas y
operadores se validan contra una lista blanca; los valores siempre van como parámetros.
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from .storage.db import quote_ident

CAPAS = ("estandarizado", "analitico")
OPERADORES = {
    "eq": "es igual a",
    "ne": "es distinto de",
    "contiene": "contiene",
    "gt": "mayor que",
    "ge": "mayor o igual que",
    "lt": "menor que",
    "le": "menor o igual que",
    "vacio": "está vacío",
    "no_vacio": "no está vacío",
}
_SQL_OP = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
# tipos a los que se convierte el valor de un filtro antes de comparar
_CASTEABLES = {"smallint", "integer", "bigint", "numeric", "real", "double precision", "text",
               "character varying", "boolean", "date", "timestamp without time zone",
               "timestamp with time zone", "uuid"}


class TablaNoExiste(LookupError):
    pass


class ConsultaInvalida(ValueError):
    """Error en lo que pidió el usuario (columna, operador o valor): se responde con 400."""


@dataclass(frozen=True)
class Filtro:
    columna: str
    operador: str
    valor: str = ""

    @classmethod
    def desde_texto(cls, texto: str) -> Filtro:
        """Formato de la API: 'columna:operador:valor'. El valor puede contener ':'."""
        partes = texto.split(":", 2)
        if len(partes) < 2:
            raise ConsultaInvalida(f"filtro inválido: {texto!r}. Usa columna:operador:valor")
        return cls(partes[0], partes[1], partes[2] if len(partes) == 3 else "")

    def como_texto(self) -> str:
        return f"{self.columna}:{self.operador}:{self.valor}"


def _tabla(capa: str, nombre: str) -> str:
    return f"{quote_ident(capa)}.{quote_ident(nombre)}"


def _escapar_like(valor: str) -> str:
    return valor.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ------------------------------------------------------------------- descubrimiento
def tablas(conn: Connection, capa: str | None = None) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text("""
        SELECT t.table_schema AS layer, t.table_name AS name, t.table_type,
               obj_description(format('%I.%I', t.table_schema, t.table_name)::regclass) AS description
        FROM information_schema.tables t
        WHERE t.table_schema IN ('estandarizado', 'analitico')
          AND (CAST(:capa AS text) IS NULL OR t.table_schema = CAST(:capa AS text))
        ORDER BY t.table_schema, t.table_name
    """), {"capa": capa}).mappings()]


def columnas(conn: Connection, capa: str, nombre: str) -> list[dict[str, Any]]:
    """Columnas de una tabla de las capas públicas, con el comentario que dbt guarda (persist_docs)."""
    if capa not in CAPAS:
        return []
    return [dict(r) for r in conn.execute(text("""
        SELECT c.column_name AS name, c.data_type AS type, d.description
        FROM information_schema.columns c
        LEFT JOIN pg_catalog.pg_description d
               ON d.objoid = format('%I.%I', c.table_schema, c.table_name)::regclass
              AND d.objsubid = c.ordinal_position
        WHERE c.table_schema = :s AND c.table_name = :t
        ORDER BY c.ordinal_position
    """), {"s": capa, "t": nombre}).mappings()]


# ------------------------------------------------------------------------ lectura
def _armar(cols: list[dict[str, Any]], filtros: Sequence[Filtro],
           orden: str | None) -> tuple[str, str, dict[str, Any]]:
    """WHERE y ORDER BY validados contra las columnas reales de la tabla."""
    tipos = {c["name"]: c["type"] for c in cols}
    partes, params = [], {}
    for i, f in enumerate(filtros):
        if f.columna not in tipos:
            raise ConsultaInvalida(f"columna desconocida: {f.columna}")
        if f.operador not in OPERADORES:
            raise ConsultaInvalida(f"operador desconocido: {f.operador}")
        col = quote_ident(f.columna)
        if f.operador == "vacio":
            partes.append(f"{col} IS NULL")
        elif f.operador == "no_vacio":
            partes.append(f"{col} IS NOT NULL")
        elif f.operador == "contiene":
            partes.append(f"CAST({col} AS text) ILIKE :f{i} ESCAPE '\\'")
            params[f"f{i}"] = f"%{_escapar_like(f.valor)}%"
        else:
            tipo = tipos[f.columna]
            valor = f"CAST(:f{i} AS {tipo})" if tipo in _CASTEABLES else f":f{i}"
            partes.append(f"{col} {_SQL_OP[f.operador]} {valor}")
            params[f"f{i}"] = f.valor
    where = (" WHERE " + " AND ".join(partes)) if partes else ""
    order = ""
    if orden:
        nombre = orden.lstrip("-")
        if nombre not in tipos:   # lista blanca: nunca se interpola texto del usuario sin validar
            raise ConsultaInvalida(f"columna desconocida: {nombre}")
        order = f" ORDER BY {quote_ident(nombre)} {'DESC' if orden.startswith('-') else 'ASC'} NULLS LAST"
    return where, order, params


def _valor_invalido(e: DBAPIError) -> ConsultaInvalida | None:
    """Convierte 'valor no válido para el tipo' en un error del usuario; el resto se propaga."""
    if getattr(e.orig, "sqlstate", "") in ("22P02", "22007", "22008", "22003"):
        return ConsultaInvalida(f"valor de filtro no válido para el tipo de la columna: {e.orig}".strip())
    return None


def _seleccion(cols: list[dict[str, Any]], solo_columnas: Sequence[str] | None) -> tuple[str, list[dict[str, Any]]]:
    """Lista del SELECT y columnas visibles. Los nombres pedidos se validan contra los reales."""
    if not solo_columnas:
        return "*", cols
    pedidas = list(dict.fromkeys(solo_columnas))
    existentes = {c["name"] for c in cols}
    if desconocidas := [c for c in pedidas if c not in existentes]:
        raise ConsultaInvalida(f"columna desconocida: {desconocidas[0]}")
    visibles = [c for c in cols if c["name"] in set(pedidas)]          # en el orden de la tabla
    return ", ".join(quote_ident(c["name"]) for c in visibles), visibles


def leer_tabla(conn: Connection, capa: str, nombre: str, filtros: Sequence[Filtro] = (),
               orden: str | None = None, limite: int = 100, desplazamiento: int = 0,
               solo_columnas: Sequence[str] | None = None) -> dict[str, Any]:
    """Filas de un dataset. `solo_columnas` limita las columnas devueltas; los filtros y el
    orden pueden usar cualquier columna de la tabla."""
    cols = columnas(conn, capa, nombre)
    if not cols:
        raise TablaNoExiste(f"dataset {capa}.{nombre} no existe")
    where, order, params = _armar(cols, filtros, orden)
    lista, visibles = _seleccion(cols, solo_columnas)
    tabla = _tabla(capa, nombre)
    try:
        total = conn.execute(text(f"SELECT count(*) FROM {tabla}{where}"), params).scalar_one()
        data = [dict(r) for r in conn.execute(
            text(f"SELECT {lista} FROM {tabla}{where}{order} LIMIT :_l OFFSET :_o"),
            {**params, "_l": limite, "_o": desplazamiento}).mappings()]
    except DBAPIError as e:
        if (err := _valor_invalido(e)) is not None:
            raise err from None
        raise
    return {"layer": capa, "name": nombre, "columns": visibles, "filters": [f.como_texto() for f in filtros],
            "total": total, "limit": limite, "offset": desplazamiento, "data": data}


# --------------------------------------------------------------------- exportación
def _celda(v: Any, decimal_coma: bool) -> Any:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (Decimal, float)) and decimal_coma:
        return str(v).replace(".", ",")
    return v


def preparar_exportacion(conn: Connection, capa: str, nombre: str, filtros: Sequence[Filtro] = (),
                         orden: str | None = None) -> tuple[str, dict[str, Any], list[str]]:
    """Valida antes de empezar a transmitir: un error a mitad de la descarga ya no se puede informar."""
    cols = columnas(conn, capa, nombre)
    if not cols:
        raise TablaNoExiste(f"dataset {capa}.{nombre} no existe")
    where, order, params = _armar(cols, filtros, orden)
    sql = f"SELECT * FROM {_tabla(capa, nombre)}{where}{order}"
    try:
        conn.execute(text(f"EXPLAIN {sql}"), params)   # detecta valores de filtro inválidos sin leer datos
    except DBAPIError as e:
        if (err := _valor_invalido(e)) is not None:
            raise err from None
        raise
    return sql, params, [c["name"] for c in cols]


def transmitir_csv(engine: Engine, sql: str, params: dict[str, Any], encabezado: list[str],
                   separador: str = ",") -> Iterator[str]:
    """CSV en UTF-8 con BOM (Excel en Windows reconoce las tildes). Con separador ';' los decimales
    llevan coma, como espera Excel con configuración regional de Colombia."""
    buf = io.StringIO()
    escritor = csv.writer(buf, delimiter=separador, lineterminator="\r\n")
    decimal_coma = separador == ";"
    yield "﻿"
    escritor.writerow(encabezado)
    with engine.connect() as conn:
        resultado = conn.execution_options(stream_results=True, max_row_buffer=2000).execute(text(sql), params)
        for i, fila in enumerate(resultado, 1):
            escritor.writerow([_celda(v, decimal_coma) for v in fila])
            if i % 2000 == 0:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
    yield buf.getvalue()
