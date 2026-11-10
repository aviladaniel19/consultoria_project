"""Motor genérico de ingesta.

Para cualquier fuente del registro:
  1. registra/actualiza la fuente en el catálogo
  2. abre una ejecución y lee el cursor incremental
  3. extrae páginas (REST o archivo) y filtra lo ya cargado
  4. infiere el esquema y lo versiona si cambió
  5. evalúa el contrato y perfila cada columna
  6. agrega los registros crudos a origen.<fuente>
  7. avanza el cursor y cierra la ejecución
  8. publica estandarizado.<fuente> (salvo que la construya un modelo dbt)

El motor de calidad MinTIC envuelve la limpieza del paso 8: evalúa los registros crudos en el
paso 5 (diagnóstico base) y la tabla publicada después del 8, y guarda el comparativo.

Los pasos 4–7 van en una sola transacción: una ejecución fallida no deja
filas a medias en la capa de origen.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import Engine

from .. import publicacion
from ..config import get_settings
from ..quality.contracts import missing_columns, run_checks
from ..quality.mintic import servicio as calidad_mintic
from ..quality.mintic.modelos import ReporteCalidad
from ..quality.mintic.util import miles
from ..quality.profiling import infer_schema, profile
from ..registry.models import SourceSpec
from ..storage import catalog
from ..storage.db import ensure_origen_table
from .file import FileExtractor
from .rest import RestExtractor

log = logging.getLogger(__name__)


class IngestionError(Exception):
    pass


@dataclass
class RunResult:
    source: str
    run_id: uuid.UUID
    status: str
    extracted: int = 0
    loaded: int = 0
    cursor_before: str | None = None
    cursor_after: str | None = None
    schema_version: int | None = None
    schema_changes: dict[str, list[str]] = field(default_factory=dict)
    failed_checks: list[str] = field(default_factory=list)
    error: str | None = None
    published: str | None = None          # tabla estandarizada publicada tras la carga
    published_rows: int | None = None
    publish_error: str | None = None
    quality_before: float | None = None   # puntaje MinTIC (0-100) de los registros crudos
    quality_after: float | None = None    # puntaje MinTIC de la tabla publicada
    quality_level: str | None = None


def _publicar(engine: Engine, spec: SourceSpec, records: list[dict], result: RunResult,
              calidad_antes: ReporteCalidad | None) -> None:
    """Publica la capa estandarizada (la limpieza) y mide su efecto en la calidad. Un fallo aquí
    no invalida la carga, que ya quedó guardada."""
    try:
        pub = publicacion.publicar(engine, spec, orden=list(dict.fromkeys(k for r in records[:1000] for k in r)))
    except Exception as e:  # noqa: BLE001
        log.error("falló la publicación de %s: %s", spec.name, e)
        result.publish_error = f"{type(e).__name__}: {e}"
        return
    if not pub:
        return
    result.published, result.published_rows = pub.tabla, pub.filas
    comparativo = calidad_mintic.evaluar_despues(engine, result.run_id, spec, pub.nombres, calidad_antes)
    if comparativo:
        result.quality_after, result.quality_level = comparativo.score_despues, comparativo.nivel_despues
    _anotar_cargue(engine, result)


def _anotar_cargue(engine: Engine, result: RunResult) -> None:
    """Deja en la bitácora del dataset la novedad de este cargue."""
    filas = miles(result.published_rows or 0)
    partes = [f"Cargue de {miles(result.loaded)} registros; el dataset quedó con {filas} filas."]
    if result.failed_checks:
        partes.append("Reglas del contrato incumplidas: " + ", ".join(result.failed_checks) + ".")
    if result.quality_before is not None and result.quality_after is not None:
        partes.append(f"Calidad MinTIC: {miles(result.quality_before, 1)} antes de la limpieza y "
                      f"{miles(result.quality_after, 1)} después (nivel {result.quality_level}).")
    try:
        with engine.begin() as conn:
            catalog.agregar_nota(conn, result.published, "cargue", " ".join(partes), "Plataforma", automatica=True)
    except Exception:  # noqa: BLE001
        log.exception("no se pudo anotar el cargue de %s en la bitácora", result.source)


# --------------------------------------------------------------- comparación
def _cmp_key(v: Any) -> tuple[int, Any]:
    """Orden robusto para cursores: número, luego fecha, luego texto."""
    try:
        return (0, float(v))
    except (TypeError, ValueError):
        pass
    ts = pd.to_datetime(str(v), errors="coerce", format="ISO8601", utc=True)
    if not pd.isna(ts):
        return (1, ts)
    return (2, str(v))


def is_after(value: Any, cursor: str | None) -> bool:
    if cursor is None:
        return True
    if value is None or value == "":   # como el '>' de SQL: un cursor nulo nunca es posterior
        return False
    a, b = _cmp_key(value), _cmp_key(cursor)
    if a[0] != b[0]:
        return str(value) > str(cursor)
    return a[1] > b[1]


def max_cursor(values: list[Any]) -> str | None:
    vals = [v for v in values if v is not None and v != ""]
    return str(max(vals, key=_cmp_key)) if vals else None


def next_cursor(values: list[Any], truncated: bool) -> str | None:
    """Nuevo cursor tras una carga. Si `max_records` cortó la extracción, el último
    valor puede haber quedado a medias (p. ej. un día con más filas que el tope):
    el cursor se queda en el valor anterior y ese grupo se vuelve a pedir en la
    siguiente ejecución. Las filas repetidas en origen se resuelven en la capa estandarizada por llave."""
    top = max_cursor(values)
    if not truncated or top is None:
        return top
    below = max_cursor([v for v in values if v is not None and v != "" and is_after(top, v)])
    if below is None:
        log.warning("todos los registros del lote comparten el cursor %s y el tope 'max_records' "
                    "los cortó: aumenta max_records o se perderán filas con ese valor", top)
        return top
    return below


def diff_schema(old: dict[str, str], new: dict[str, str]) -> tuple[dict[str, str], list[str], list[str]]:
    """Esquema acumulado + columnas nuevas + columnas que cambiaron de tipo.
    'unknown' (todo nulo en el lote) nunca sobrescribe un tipo conocido."""
    merged = dict(old)
    added, retyped = [], []
    for col, typ in new.items():
        if col not in old:
            merged[col] = typ
            added.append(col)
        elif typ != "unknown" and old[col] == "unknown":
            merged[col] = typ
        elif typ not in ("unknown", old[col]):
            merged[col] = typ
            retyped.append(col)
    return merged, sorted(added), sorted(retyped)


# ------------------------------------------------------------------- extracción
def make_extractor(spec: SourceSpec, cursor: str | None, client: httpx.Client | None = None):
    if spec.type == "rest":
        return RestExtractor(spec, cursor, client=client)
    return FileExtractor(spec, cursor)


def extract(spec: SourceSpec, cursor: str | None, client: httpx.Client | None = None) -> tuple[list[dict], int]:
    """Devuelve (registros nuevos, registros extraídos antes de filtrar)."""
    inc = spec.incremental
    records: list[dict] = []
    extracted = 0
    for page in make_extractor(spec, cursor, client).pages():
        extracted += len(page)
        if inc and cursor is not None:
            page = [r for r in page if is_after(r.get(inc.cursor_field), cursor)]
        records.extend(page)
    return records, extracted


# ---------------------------------------------------------------------- motor
def run_source(engine: Engine, spec: SourceSpec, client: httpx.Client | None = None,
               full_refresh: bool = False, publish: bool = True) -> RunResult:
    run_id = uuid.uuid4()
    with engine.begin() as conn:
        catalog.register_source(conn, spec)
        stored = None if full_refresh else catalog.get_cursor(conn, spec.name)
        cursor = stored if stored is not None else (spec.incremental.initial_value if spec.incremental else None)
        catalog.start_run(conn, run_id, spec.name, cursor)

    result = RunResult(source=spec.name, run_id=run_id, status="running", cursor_before=cursor)
    calidad_antes: ReporteCalidad | None = None
    try:
        ensure_origen_table(engine, spec.origen_table)
        records, result.extracted = extract(spec, cursor, client)
        with engine.begin() as conn:
            if not records:
                result.status = "success"
                result.cursor_after = cursor
                catalog.finish_run(conn, run_id, "success", extracted=result.extracted, cursor_after=cursor)
                return result

            df = pd.DataFrame.from_records(records)

            missing = missing_columns(df, spec.contract)
            if missing:
                raise IngestionError(f"faltan columnas obligatorias: {', '.join(missing)}")

            batch_schema = infer_schema(df)
            prev = catalog.latest_schema(conn, spec.name)
            old_cols = prev[1] if prev else {}
            merged, added, retyped = diff_schema(old_cols, batch_schema)
            version = prev[0] if prev else 0
            if added or retyped or prev is None:
                if prev is not None and spec.contract.on_schema_change == "fail":
                    raise IngestionError(f"cambio de esquema no permitido (nuevas: {added}, retipadas: {retyped})")
                version += 1
                catalog.save_schema_version(conn, spec.name, version, merged, added, retyped, run_id)
                result.schema_changes = {"added": added, "retyped": retyped}
            result.schema_version = version

            checks = run_checks(df, spec.contract)
            catalog.save_quality(conn, run_id, spec.name, (c.as_row() for c in checks))
            catalog.save_profiles(conn, run_id, spec.name, (p.as_row() for p in profile(df, batch_schema)))

            calidad_antes = calidad_mintic.evaluar_antes(conn, run_id, spec, df)   # diagnóstico base
            if calidad_antes:
                result.quality_before = calidad_antes.score_global
                result.quality_level = calidad_antes.nivel_cumplimiento

            result.failed_checks = [f"{c.column_name}:{c.rule}" for c in checks if not c.passed]
            if any(not c.passed and c.severity == "error" for c in checks):
                result.status = "failed_quality"     # se carga, pero dbt lo deja en cuarentena
            elif result.failed_checks:
                result.status = "success_with_warnings"
            else:
                result.status = "success"

            result.loaded = catalog.insert_origen(conn, spec.origen_table, run_id, records,
                                                  get_settings().origen_batch_size)

            result.cursor_after = cursor
            if spec.incremental:
                truncated = spec.max_records is not None and result.extracted >= spec.max_records
                new_max = next_cursor([r.get(spec.incremental.cursor_field) for r in records], truncated)
                if new_max is not None and is_after(new_max, cursor):
                    result.cursor_after = new_max
                    catalog.set_cursor(conn, spec.name, new_max)

            catalog.finish_run(conn, run_id, result.status, extracted=result.extracted,
                               loaded=result.loaded, cursor_after=result.cursor_after,
                               schema_version=version)
        if publish and result.status in publicacion.APROBADAS:
            _publicar(engine, spec, records, result, calidad_antes)
        return result
    except Exception as e:  # noqa: BLE001 — cualquier falla queda registrada en el catálogo
        log.error("falló la ingesta de %s: %s", spec.name, e)
        log.debug("detalle", exc_info=True)
        result.status, result.error = "failed", f"{type(e).__name__}: {e}"
        with engine.begin() as conn:
            catalog.finish_run(conn, run_id, "failed", extracted=result.extracted, error=result.error[:2000])
        return result
