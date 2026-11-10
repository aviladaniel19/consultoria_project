"""Consultas de las pantallas del frontend: catálogo, ficha, perfiles, calidad, salud y buscador."""
from __future__ import annotations

import math
import unicodedata
from typing import Any

from sqlalchemy import Connection, text

from .. import consultas, indicadores
from ..publicacion import METADATOS, nombre_columna
from ..quality.mintic import servicio as calidad_mintic
from ..storage.db import quote_ident

NUMERICOS = {"smallint", "integer", "bigint", "numeric", "real", "double precision"}
TEMPORALES = {"date", "timestamp without time zone", "timestamp with time zone"}
BARRAS = 20


def normalizar(s: str | None) -> str:
    """Minúsculas y sin tildes, para que 'contratacion' encuentre 'contratación'."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def titulo_y_descripcion(comentario: str | None, nombre: str) -> tuple[str, str]:
    """Convención de schema.yml: primera línea = título. Sin comentario, se humaniza el nombre."""
    if comentario and comentario.strip():
        primera, _, resto = comentario.strip().partition("\n")
        return primera.strip(), resto.strip()
    return nombre.replace("_", " ").capitalize(), ""


def tipo_legible(tipo: str) -> str:
    if tipo in NUMERICOS:
        return "número"
    if tipo in TEMPORALES:
        return "fecha"
    if tipo in ("text", "character varying"):
        return "texto"
    if tipo == "boolean":
        return "sí/no"
    return tipo


# -------------------------------------------------------------------------- catálogo
def _fuentes(conn: Connection) -> dict[str, dict[str, Any]]:
    """Fuentes del registro con su última carga, indexadas por nombre."""
    filas = conn.execute(text("""
        SELECT s.name, s.description, s.tags, s.type, s.enabled, s.owner, s.spec,
               r.status AS ultimo_estado, r.finished_at AS ultima_carga, r.records_loaded AS ultimos_registros,
               st.cursor_value AS cursor
        FROM meta.sources s
        LEFT JOIN meta.state st ON st.source_name = s.name
        LEFT JOIN LATERAL (
            SELECT status, finished_at, records_loaded FROM meta.runs
            WHERE source_name = s.name ORDER BY started_at DESC LIMIT 1
        ) r ON true
        ORDER BY s.name
    """)).mappings()
    return {f["name"]: dict(f) for f in filas}


def _construcciones(conn: Connection) -> dict[str, tuple[Any, int | None]]:
    """tabla -> (cuándo se construyó, filas al construirse)."""
    return {t: (en, filas) for t, en, filas in conn.execute(text(
        "SELECT tabla, construida_en, filas FROM meta.construcciones"))}


def _filas(conn: Connection, capa: str, nombre: str, guardadas: int | None) -> int:
    """Filas de la tabla. Se guardan al construirla (publicación o dbt); solo las tablas sin ese
    dato, construidas por fuera o antes de existir la columna, se cuentan."""
    if guardadas is not None:
        return guardadas
    return conn.execute(text(f"SELECT count(*) FROM {quote_ident(capa)}.{quote_ident(nombre)}")).scalar_one()


def catalogo(conn: Connection, q: str | None = None, etiqueta: str | None = None) -> list[dict[str, Any]]:
    fuentes = _fuentes(conn)
    construidas = _construcciones(conn)
    cols_por_tabla: dict[tuple[str, str], list[str]] = {}
    for capa, tabla, col in conn.execute(text("""
        SELECT table_schema, table_name, column_name FROM information_schema.columns
        WHERE table_schema IN ('estandarizado', 'analitico') ORDER BY ordinal_position
    """)):
        cols_por_tabla.setdefault((capa, tabla), []).append(col)

    buscado = normalizar(q).strip()
    items = []
    for t in consultas.tablas(conn):
        capa, nombre = t["layer"], t["name"]
        titulo, descripcion = titulo_y_descripcion(t["description"], nombre)
        fuente = fuentes.get(nombre)          # una tabla estandarizada se llama como su fuente
        etiquetas = list(fuente["tags"]) if fuente else []
        cols = cols_por_tabla.get((capa, nombre), [])
        if etiqueta and etiqueta not in etiquetas:
            continue
        if buscado and buscado not in normalizar(" ".join([titulo, descripcion, nombre, *cols, *etiquetas])):
            continue
        construida_en, guardadas = construidas.get(f"{capa}.{nombre}", (None, None))
        items.append({
            "capa": capa, "nombre": nombre, "titulo": titulo, "descripcion": descripcion,
            "filas": _filas(conn, capa, nombre, guardadas), "n_columnas": len(cols), "etiquetas": etiquetas,
            "construida_en": construida_en,
            "fuente": fuente,
        })
    return items


def etiquetas(conn: Connection) -> list[str]:
    return [r[0] for r in conn.execute(text(
        "SELECT DISTINCT unnest(tags) FROM meta.sources WHERE enabled ORDER BY 1"))]


# ----------------------------------------------------------------------------- ficha
def ficha(conn: Connection, capa: str, nombre: str) -> dict[str, Any]:
    cols = consultas.columnas(conn, capa, nombre)
    if not cols:
        raise consultas.TablaNoExiste(f"dataset {capa}.{nombre} no existe")
    comentario = conn.execute(text(
        "SELECT obj_description(format('%I.%I', CAST(:s AS text), CAST(:t AS text))::regclass)"),
        {"s": capa, "t": nombre}).scalar()
    titulo, descripcion = titulo_y_descripcion(comentario, nombre)
    fila = conn.execute(text("SELECT construida_en, filas, columnas FROM meta.construcciones WHERE tabla = :t"),
                        {"t": f"{capa}.{nombre}"}).first()
    construida, guardadas, nombres = fila if fila else (None, None, None)
    filas = _filas(conn, capa, nombre, guardadas)
    for c in cols:
        c["tipo"] = tipo_legible(c["type"])
    return {"capa": capa, "nombre": nombre, "titulo": titulo, "descripcion": descripcion,
            "columnas": cols, "filas": filas, "construida_en": construida,
            "nombres": nombres or {},                      # columna en la fuente -> columna publicada
            "fuente": _fuentes(conn).get(nombre) if capa == "estandarizado" else None}


def columnas_vista(f: dict[str, Any]) -> list[str] | None:
    """Columnas que muestra la vista previa: las seleccionadas al cargar la fuente
    (`preview_columns`); si no se eligieron, la llave y las obligatorias. None = todas."""
    spec = (f.get("fuente") or {}).get("spec") or {}
    elegidas = spec.get("preview_columns") or [
        *spec.get("primary_key", []), *spec.get("contract", {}).get("required_columns", [])]
    existentes = {c["name"] for c in f["columnas"]}
    publicadas = {f["nombres"].get(c) or nombre_columna(c, set()) for c in elegidas}
    visibles = [c["name"] for c in f["columnas"] if c["name"] in publicadas & existentes]
    return visibles if visibles and len(visibles) < len([c for c in existentes if c not in METADATOS]) else None


# ------------------------------------------------------------------------ bitácora
def notas(conn: Connection, tabla: str) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text("""
        SELECT id, tabla, categoria, texto, autor, automatica, creada_en, editada_en
        FROM meta.bitacora WHERE tabla = :t ORDER BY creada_en DESC, id DESC
    """), {"t": tabla}).mappings()]


def nota(conn: Connection, nota_id: int) -> dict[str, Any] | None:
    r = conn.execute(text("""
        SELECT id, tabla, categoria, texto, autor, automatica, creada_en, editada_en
        FROM meta.bitacora WHERE id = :id"""), {"id": nota_id}).mappings().first()
    return dict(r) if r else None


# --------------------------------------------------------------------- indicadores
_TIPO_INDICADOR = {"número": "numero", "fecha": "fecha", "texto": "texto", "sí/no": "booleano"}


def sugerencias_indicadores(conn: Connection, f: dict[str, Any]) -> dict[str, Any]:
    """Indicadores sugeridos para el dataset, según su esquema y su tema."""
    tabla = f"{quote_ident(f['capa'])}.{quote_ident(f['nombre'])}"
    cols = [c for c in f["columnas"] if c["name"] not in METADATOS]
    contables = [c["name"] for c in cols if c["tipo"] in ("texto", "sí/no")]
    distintos: dict[str, int] = {}
    if contables:      # una sola consulta para todas las columnas de texto
        fila = conn.execute(text("SELECT " + ", ".join(
            f"count(DISTINCT {quote_ident(c)})" for c in contables) + f" FROM {tabla}")).one()
        distintos = dict(zip(contables, fila, strict=True))
    fuente = f.get("fuente") or {}
    personales = calidad_mintic.columnas_con_datos_personales(conn, fuente["name"]) if fuente else set()
    columnas = [indicadores.Columna(c["name"], _TIPO_INDICADOR.get(c["tipo"], "otro"), distintos.get(c["name"]))
                for c in cols]
    lista = indicadores.sugerir(f"{f['capa']}.{f['nombre']}", columnas, f["titulo"], f["descripcion"],
                                fuente.get("tags") or [], f["filas"], excluir=sorted(personales))
    grupos: dict[str, list[indicadores.Sugerencia]] = {}
    for s in lista:
        grupos.setdefault(s.grupo, []).append(s)
    return {"grupos": grupos, "temas": indicadores.temas_de(f["titulo"], f["descripcion"], fuente.get("tags") or [],
                                                            columnas), "personales": sorted(personales)}


def _histograma(conn: Connection, tabla: str, expr: str, lo: float, hi: float) -> list[float]:
    """Alturas relativas (0-1) de BARRAS intervalos iguales entre lo y hi."""
    conteo = [0] * BARRAS
    for b, n in conn.execute(text(f"""
        SELECT least(width_bucket(x, :lo, :hi, {BARRAS}), {BARRAS}) AS b, count(*)
        FROM (SELECT {expr} AS x FROM {tabla}) s WHERE x IS NOT NULL GROUP BY 1
    """), {"lo": lo, "hi": hi}):
        conteo[max(1, b) - 1] += n
    pico = max(conteo) or 1
    return [n / pico for n in conteo]


def perfil_columnas(conn: Connection, capa: str, nombre: str) -> list[dict[str, Any]]:
    """Resumen estadístico de cada columna, calculado sobre la tabla completa."""
    tabla = f"{quote_ident(capa)}.{quote_ident(nombre)}"
    perfiles = []
    for c in consultas.columnas(conn, capa, nombre):
        if c["name"] in METADATOS:           # trazabilidad interna: está en la tabla, no aporta al perfil
            continue
        col, tipo = quote_ident(c["name"]), c["type"]
        p: dict[str, Any] = {"nombre": c["name"], "tipo": tipo_legible(tipo), "descripcion": c["description"]}
        if tipo in NUMERICOS:
            r = conn.execute(text(f"""
                SELECT count(*) AS n, count({col}) AS no_nulos, count(DISTINCT {col}) AS distintos,
                       min({col})::float8 AS minimo, max({col})::float8 AS maximo,
                       avg({col})::float8 AS media, stddev_samp({col})::float8 AS desviacion,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY {col})::float8 AS mediana
                FROM {tabla}""")).mappings().one()
            p.update(r)
            if r["no_nulos"] and r["minimo"] < r["maximo"]:
                # distribuciones muy sesgadas (precios, montos) se leen mejor en escala logarítmica
                log = r["minimo"] >= 0 and r["maximo"] > 50 * max(r["mediana"] or 0, 1e-9)
                if log:
                    p["hist"] = _histograma(conn, tabla, f"ln(1 + {col}::float8)",
                                            math.log1p(r["minimo"]), math.log1p(r["maximo"]))
                else:
                    p["hist"] = _histograma(conn, tabla, f"{col}::float8", r["minimo"], r["maximo"])
                p["escala"] = "logarítmica" if log else "lineal"
        elif tipo in TEMPORALES:
            r = conn.execute(text(f"""
                SELECT count(*) AS n, count({col}) AS no_nulos, count(DISTINCT {col}) AS distintos,
                       min({col}) AS minimo, max({col}) AS maximo,
                       extract(epoch FROM min({col}))::float8 AS e_min, extract(epoch FROM max({col}))::float8 AS e_max
                FROM {tabla}""")).mappings().one()
            p.update(r)
            if r["no_nulos"] and r["e_min"] < r["e_max"]:
                p["hist"] = _histograma(conn, tabla, f"extract(epoch FROM {col})::float8", r["e_min"], r["e_max"])
                p["escala"] = "lineal"
        else:
            r = conn.execute(text(f"""
                SELECT count(*) AS n, count({col}) AS no_nulos, count(DISTINCT CAST({col} AS text)) AS distintos
                FROM {tabla}""")).mappings().one()
            p.update(r)
            p["frecuentes"] = [dict(f) for f in conn.execute(text(f"""
                SELECT CAST({col} AS text) AS valor, count(*) AS n FROM {tabla}
                WHERE {col} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 3""")).mappings()]
        p["nulos_pct"] = 1 - (p["no_nulos"] / p["n"]) if p["n"] else 0.0
        perfiles.append(p)
    return perfiles


# -------------------------------------------------------------------------- calidad
def cargas(conn: Connection, fuente: str, limite: int = 30) -> list[dict[str, Any]]:
    """Últimas cargas de una fuente, de la más antigua a la más reciente."""
    filas = [dict(r) for r in conn.execute(text("""
        SELECT run_id, started_at, finished_at, status, records_extracted, records_loaded,
               cursor_after, schema_version, error
        FROM meta.runs WHERE source_name = :f ORDER BY started_at DESC LIMIT :l
    """), {"f": fuente, "l": limite}).mappings()]
    return filas[::-1]


def reglas_ultima_carga(conn: Connection, fuente: str) -> list[dict[str, Any]]:
    """Resultado de cada regla del contrato en la última carga que trajo datos."""
    return [dict(r) for r in conn.execute(text("""
        SELECT q.column_name, q.rule, q.severity, q.total, q.failed, q.failure_rate, q.threshold,
               q.passed, q.detail
        FROM meta.quality_results q
        WHERE q.run_id = (SELECT run_id FROM meta.runs WHERE source_name = :f AND records_loaded > 0
                          ORDER BY started_at DESC LIMIT 1)
        ORDER BY q.passed, q.column_name
    """), {"f": fuente}).mappings()]


GRUPOS_TIPO = {"numeric": "Numéricos", "text": "Texto", "datetime": "Fechas", "boolean": "Sí/No"}


def perfiles_por_tipo(conn: Connection, fuente: str) -> list[dict[str, Any]]:
    """Salud de los datos de la última carga con registros, agrupada por tipo de dato:
    [{'tipo', 'columnas': [...], 'vacios_promedio'}], en el orden Numéricos, Texto, Fechas, Sí/No, Otros."""
    filas = conn.execute(text("""
        SELECT column_name, inferred_type, n, null_rate, n_distinct, min_value, max_value, mean, p50
        FROM meta.column_profiles
        WHERE run_id = (SELECT run_id FROM meta.runs WHERE source_name = :f AND records_loaded > 0
                        ORDER BY started_at DESC LIMIT 1)
        ORDER BY null_rate DESC, column_name
    """), {"f": fuente}).mappings().all()
    grupos: dict[str, list[dict[str, Any]]] = {g: [] for g in [*GRUPOS_TIPO.values(), "Otros"]}
    for r in filas:
        grupos[GRUPOS_TIPO.get(r["inferred_type"], "Otros")].append(dict(r))
    return [{"tipo": tipo, "columnas": cols, "vacios_promedio": sum(c["null_rate"] for c in cols) / len(cols),
             "con_vacios": sum(1 for c in cols if c["null_rate"] > 0)}
            for tipo, cols in grupos.items() if cols]


def salud(conn: Connection) -> list[dict[str, Any]]:
    resultado = []
    for nombre, f in _fuentes(conn).items():
        resultado.append({**f, "cargas": cargas(conn, nombre),
                          "incumplidas": [r for r in reglas_ultima_carga(conn, nombre) if not r["passed"]],
                          "tipos": perfiles_por_tipo(conn, nombre)})
    return resultado


# -------------------------------------------------------------------------- buscador
def buscar(conn: Connection, q: str, limite: int = 8) -> list[dict[str, Any]]:
    """Datasets, columnas y fuentes que coinciden con el texto, para el buscador universal."""
    buscado = normalizar(q).strip()
    if not buscado:
        return []
    items: list[dict[str, Any]] = []
    for t in consultas.tablas(conn):
        titulo, descripcion = titulo_y_descripcion(t["description"], t["name"])
        if buscado in normalizar(f"{titulo} {descripcion} {t['name']}"):
            items.append({"tipo": "Dataset", "texto": titulo, "detalle": f"{t['layer']}.{t['name']}",
                          "url": f"/datos/{t['layer']}/{t['name']}"})
    for capa, tabla, col in conn.execute(text("""
        SELECT table_schema, table_name, column_name FROM information_schema.columns
        WHERE table_schema IN ('estandarizado', 'analitico') ORDER BY table_schema, table_name, ordinal_position
    """)):
        if buscado in normalizar(col):
            items.append({"tipo": "Columna", "texto": col, "detalle": f"en {capa}.{tabla}",
                          "url": f"/datos/{capa}/{tabla}#columnas"})
    for nombre, f in _fuentes(conn).items():
        if buscado in normalizar(f"{nombre} {f['description']} {' '.join(f['tags'])}"):
            items.append({"tipo": "Fuente", "texto": nombre, "detalle": f["description"],
                          "url": f"/salud#fuente-{nombre}"})
    return items[:limite]
