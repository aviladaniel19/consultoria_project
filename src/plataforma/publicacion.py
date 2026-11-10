"""Publicación automática de la capa estandarizada.

Después de cada carga construye `estandarizado.<fuente>` a partir de la capa de origen:
tipos según el esquema inferido, nombres de columna limpios (minúsculas, sin tildes ni
espacios), sin duplicados por llave y sin las cargas en cuarentena. Así una fuente nueva
aparece en el catálogo, la API, el explorador y el servidor MCP sin escribir SQL.

Si un modelo dbt curado construye esa tabla (meta.construcciones.construida_por = 'dbt'),
la publicación automática no la toca.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from psycopg import sql
from sqlalchemy import Engine, text

from .registry.models import SourceSpec
from .storage import catalog

CAPA = "estandarizado"
APROBADAS = ("success", "success_with_warnings")
METADATOS = ("cargado_en", "id_carga")   # columnas que agrega la plataforma


@dataclass
class Publicacion:
    tabla: str
    filas: int
    columnas: int
    nombres: dict[str, str] = field(default_factory=dict)   # columna en la fuente -> columna publicada


def nombre_columna(original: str, usados: set[str]) -> str:
    """'Fecha de Publicación' -> 'fecha_de_publicacion'. Evita repetidos y nombres inválidos."""
    s = unicodedata.normalize("NFKD", str(original))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "columna"
    if s[0].isdigit():
        s = f"c_{s}"
    s, base, i = s[:63], s[:58], 2
    while s in usados:
        s, i = f"{base}_{i}", i + 1
    usados.add(s)
    return s


def _expresion(clave: str, tipo: str) -> sql.Composable:
    campo = sql.SQL("rec ->> {}").format(sql.Literal(clave))
    funcion = {"numeric": "a_numero", "datetime": "a_fecha", "boolean": "a_booleano"}.get(tipo)
    if funcion:
        return sql.SQL("meta.{}({})").format(sql.Identifier(funcion), campo)
    if tipo == "object":
        return sql.SQL("rec -> {}").format(sql.Literal(clave))
    return campo


def _seleccion(spec: SourceSpec) -> sql.Composable:
    """Registros vigentes de la capa de origen, solo de cargas aprobadas."""
    origen = sql.SQL("origen.{}").format(sql.Identifier(spec.origen_table))
    aprobadas = sql.SQL("""
        SELECT b._record AS rec, b._loaded_at, b._id, b._run_id
        FROM {origen} b JOIN meta.runs r ON r.run_id = b._run_id
        WHERE r.status IN ('success', 'success_with_warnings')""").format(origen=origen)
    if spec.primary_key:
        # la carga más reciente gana cuando la llave se repite
        llave = sql.SQL(", ").join(sql.SQL("rec ->> {}").format(sql.Literal(k)) for k in spec.primary_key)
        return sql.SQL("""
            SELECT * FROM (
                SELECT a.*, row_number() OVER (PARTITION BY {llave} ORDER BY _loaded_at DESC, _id DESC) AS _rn
                FROM ({aprobadas}) a
            ) v WHERE _rn = 1""").format(llave=llave, aprobadas=aprobadas)
    if spec.incremental:
        return aprobadas                     # cada carga trae solo lo nuevo: se acumulan
    # sin llave ni cursor, cada carga es una foto completa: vale solo la última aprobada
    return sql.SQL("""
        SELECT * FROM ({aprobadas}) a
        WHERE a._run_id = (SELECT run_id FROM meta.runs
                           WHERE source_name = {fuente} AND status IN ('success', 'success_with_warnings')
                             AND records_loaded > 0
                           ORDER BY started_at DESC LIMIT 1)""").format(
        aprobadas=aprobadas, fuente=sql.Literal(spec.name))


def publicar(engine: Engine, spec: SourceSpec, orden: Sequence[str] = ()) -> Publicacion | None:
    """Reconstruye la tabla estandarizada de la fuente. Devuelve None si no aplica: sin datos
    todavía o porque un modelo dbt se encarga de ella. `orden` conserva el orden original de las
    columnas (jsonb no lo guarda)."""
    tabla = f"{CAPA}.{spec.name}"
    with engine.begin() as conn:
        duenio = conn.execute(text("SELECT construida_por FROM meta.construcciones WHERE tabla = :t"),
                              {"t": tabla}).scalar()
        if duenio == "dbt":
            return None
        esquema = catalog.latest_schema(conn, spec.name)
        if esquema is None:
            return None
        tipos = esquema[1]
        claves = [c for c in dict.fromkeys(orden) if c in tipos] + sorted(c for c in tipos if c not in orden)

        usados = set(METADATOS)
        nombres = {c: nombre_columna(c, usados) for c in claves}
        columnas = [sql.SQL("{} AS {}").format(_expresion(c, tipos[c]), sql.Identifier(nombres[c])) for c in claves]
        columnas += [sql.SQL("_loaded_at AS cargado_en"), sql.SQL("_run_id AS id_carga")]

        nueva = sql.Identifier(f"_nueva_{spec.name}"[:63])
        destino = sql.Identifier(spec.name)
        titulo = spec.title or spec.name.replace("_", " ").capitalize()
        # cursor del driver con composición de psycopg: claves y textos van escapados como literales
        cur = conn.connection.driver_connection.cursor()
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{}").format(sql.Identifier(CAPA), nueva))
        cur.execute(sql.SQL("CREATE TABLE {}.{} AS SELECT {} FROM ({}) s").format(
            sql.Identifier(CAPA), nueva, sql.SQL(", ").join(columnas), _seleccion(spec)))
        filas = cur.rowcount                  # CREATE TABLE AS informa las filas: sin un count(*) aparte
        # Todo lo que se puede hacer sobre la tabla nueva va antes de tocar la publicada: el DROP
        # toma un bloqueo exclusivo que dura hasta el commit, y así ese tramo queda en lo mínimo.
        cur.execute(sql.SQL("COMMENT ON TABLE {}.{} IS {}").format(
            sql.Identifier(CAPA), nueva, sql.Literal(f"{titulo}\n{spec.description}")))
        descripciones = spec.metadata.column_descriptions
        comentarios = {}
        for c in claves:
            original = f"Nombre original en la fuente: {c}" if nombres[c] != c else ""
            if texto := " ".join(p for p in ((descripciones.get(c) or "").strip(), original) if p):
                comentarios[nombres[c]] = texto
        comentarios |= {"cargado_en": "Momento en que la plataforma cargó el registro.",
                        "id_carga": "Carga que trajo el registro (trazabilidad)."}
        for columna, comentario in comentarios.items():
            cur.execute(sql.SQL("COMMENT ON COLUMN {}.{}.{} IS {}").format(
                sql.Identifier(CAPA), nueva, sql.Identifier(columna), sql.Literal(comentario)))
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{}").format(sql.Identifier(CAPA), destino))
        cur.execute(sql.SQL("ALTER TABLE {}.{} RENAME TO {}").format(sql.Identifier(CAPA), nueva, destino))
        conn.execute(text("""
            INSERT INTO meta.construcciones (tabla, construida_en, construida_por, filas, columnas)
            VALUES (:t, now(), 'plataforma', :f, CAST(:c AS jsonb))
            ON CONFLICT (tabla) DO UPDATE SET construida_en = excluded.construida_en,
                construida_por = 'plataforma', filas = excluded.filas, columnas = excluded.columnas
        """), {"t": tabla, "f": filas, "c": json.dumps(nombres, ensure_ascii=False)})
    return Publicacion(tabla=tabla, filas=filas, columnas=len(claves), nombres=nombres)


def despublicar(engine: Engine, nombre: str) -> None:
    """Elimina la tabla estandarizada de una fuente, solo si la creó la publicación automática."""
    tabla = f"{CAPA}.{nombre}"
    with engine.begin() as conn:
        duenio = conn.execute(text("SELECT construida_por FROM meta.construcciones WHERE tabla = :t"),
                              {"t": tabla}).scalar()
        if duenio == "plataforma":
            conn.connection.driver_connection.execute(
                sql.SQL("DROP TABLE IF EXISTS {}.{}").format(sql.Identifier(CAPA), sql.Identifier(nombre)))
            conn.execute(text("DELETE FROM meta.construcciones WHERE tabla = :t"), {"t": tabla})
