"""Conexión del motor MinTIC con la plataforma: evalúa cada carga antes y después de la limpieza
(la publicación de la capa estandarizada) y guarda los reportes en `meta.calidad_mintic`.

Nada de aquí puede hacer fallar una carga: cualquier error se registra y se sigue adelante.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy import Connection, Engine, text

from ...config import get_settings
from ...registry.models import SourceSpec
from ...storage.db import quote_ident
from .modelos import MetadatosDCAT, ReporteCalidad, ReporteComparativo
from .motor import MinTicQualityEngine

log = logging.getLogger(__name__)
CAPA = "estandarizado"
COLUMNAS_INTERNAS = ("cargado_en", "id_carga")     # trazabilidad que agrega la plataforma
MOTOR = MinTicQualityEngine()


def metadatos_de(spec: SourceSpec) -> MetadatosDCAT:
    """Metadatos DCAT a partir del YAML de la fuente."""
    m = spec.metadata
    return MetadatosDCAT(
        titulo=spec.title or spec.name.replace("_", " ").capitalize(), descripcion=spec.description,
        entidad=m.publisher, correo=m.contact_email, usuario_publicador=spec.owner, categoria=m.category,
        frecuencia=m.update_frequency, cobertura=m.coverage, licencia=m.license, etiquetas=spec.tags,
        descripciones_columnas=m.column_descriptions, llave=spec.primary_key)


def _guardar(conn: Connection, run_id: UUID, fuente: str, reporte: ReporteCalidad,
             comparativo: ReporteComparativo | None = None) -> None:
    conn.execute(text("""
        INSERT INTO meta.calidad_mintic (run_id, source_name, etapa, score, nivel, reporte, comparativo)
        VALUES (:run, :src, :etapa, :score, :nivel, CAST(:rep AS jsonb), CAST(:comp AS jsonb))
        ON CONFLICT (run_id, etapa) DO UPDATE SET score = excluded.score, nivel = excluded.nivel,
            reporte = excluded.reporte, comparativo = excluded.comparativo, creada_en = now()
    """), dict(run=run_id, src=fuente, etapa=reporte.etapa, score=reporte.score_global,
               nivel=reporte.nivel_cumplimiento, rep=reporte.model_dump_json(),
               comp=comparativo.model_dump_json() if comparativo else None))


def evaluar_antes(conn: Connection, run_id: UUID, spec: SourceSpec, df: pd.DataFrame) -> ReporteCalidad | None:
    """Diagnóstico base: los registros tal como llegaron de la fuente."""
    try:
        reporte = MOTOR.evaluar(df, metadatos_de(spec), "antes")
        with conn.begin_nested():          # si el guardado falla, la transacción de la carga sigue sana
            _guardar(conn, run_id, spec.name, reporte)
        return reporte
    except Exception:
        log.exception("falló la evaluación de calidad (antes) de %s", spec.name)
        return None


def evaluar_despues(engine: Engine, run_id: UUID, spec: SourceSpec, nombres: dict[str, str],
                    antes: ReporteCalidad | None) -> ReporteComparativo | None:
    """Diagnóstico final sobre la tabla publicada y comparativo con el diagnóstico base."""
    try:
        tabla = f"{quote_ident(CAPA)}.{quote_ident(spec.name)}"
        limite = get_settings().calidad_max_filas
        with engine.connect() as conn:
            total = conn.execute(text(f"SELECT count(*) FROM {tabla}")).scalar_one()
            muestra = total > limite
            consulta = f"SELECT * FROM {tabla}" + (f" ORDER BY random() LIMIT {int(limite)}" if muestra else "")
            df = pd.read_sql(text(consulta), conn)
        df = df.drop(columns=[c for c in COLUMNAS_INTERNAS if c in df.columns])
        reporte = MOTOR.evaluar(df, metadatos_de(spec).renombrar(nombres), "despues", muestra=muestra)
        comparativo = MOTOR.comparar(antes, reporte, nombres) if antes else None
        with engine.begin() as conn:
            _guardar(conn, run_id, spec.name, reporte, comparativo)
        return comparativo
    except Exception:
        log.exception("falló la evaluación de calidad (después) de %s", spec.name)
        return None


def ultimo(conn: Connection, fuente: str) -> dict[str, Any] | None:
    """Reportes de la última carga evaluada: {'antes', 'despues', 'comparativo', 'creada_en'}."""
    filas = conn.execute(text("""
        SELECT etapa, reporte, comparativo, creada_en FROM meta.calidad_mintic
        WHERE run_id = (SELECT run_id FROM meta.calidad_mintic WHERE source_name = :s
                        ORDER BY creada_en DESC LIMIT 1)
    """), {"s": fuente}).mappings().all()
    if not filas:
        return None
    out: dict[str, Any] = {"antes": None, "despues": None, "comparativo": None,
                           "creada_en": max(f["creada_en"] for f in filas)}
    for f in filas:
        out[f["etapa"]] = f["reporte"]
        if f["comparativo"]:
            out["comparativo"] = f["comparativo"]
    return out


def columnas_con_datos_personales(conn: Connection, fuente: str) -> set[str]:
    """Columnas publicadas que el motor marcó con ERR018 en la última evaluación."""
    r = ultimo(conn, fuente)
    reporte = (r or {}).get("despues") or (r or {}).get("antes") or {}
    return {h["columna"] for h in reporte.get("hallazgos_errores", []) if h["codigo"] == "ERR018" and h["columna"]}
