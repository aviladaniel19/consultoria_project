"""Lectura y escritura del catálogo (`meta.*`) y de la capa de origen."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text

from ..registry.models import SourceSpec
from .db import quote_ident

SECRET_KEYS = {"value", "token"}
# headers y params fijos también pueden llevar credenciales (Authorization, api_key, ...)
SECRET_NAME = re.compile(r"auth|token|key|secret|passw|signature|credential", re.IGNORECASE)


def redacted_spec(spec: SourceSpec) -> dict[str, Any]:
    """Volcado del YAML sin secretos, para guardarlo en el catálogo."""
    data = spec.model_dump(mode="json")
    conn = data.get("connection", {})
    auth = conn.get("auth")
    if isinstance(auth, dict):
        for k in SECRET_KEYS & auth.keys():
            if auth[k]:
                auth[k] = "***"
    for block in ("headers", "params"):
        values = conn.get(block)
        if isinstance(values, dict):
            for k in values:
                if SECRET_NAME.search(k) and values[k]:
                    values[k] = "***"
    return data


def register_source(conn: Connection, spec: SourceSpec) -> None:
    data = redacted_spec(spec)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    conn.execute(text("""
        INSERT INTO meta.sources (name, description, owner, tags, type, enabled, spec, spec_hash)
        VALUES (:name, :description, :owner, :tags, :type, :enabled, CAST(:spec AS jsonb), :hash)
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description, owner = EXCLUDED.owner, tags = EXCLUDED.tags,
            type = EXCLUDED.type, enabled = EXCLUDED.enabled, spec = EXCLUDED.spec,
            spec_hash = EXCLUDED.spec_hash,
            updated_at = CASE WHEN meta.sources.spec_hash <> EXCLUDED.spec_hash
                              THEN now() ELSE meta.sources.updated_at END
    """), dict(name=spec.name, description=spec.description, owner=spec.owner, tags=spec.tags,
               type=spec.type, enabled=spec.enabled, spec=json.dumps(data), hash=digest))


# ------------------------------------------------------------------ ejecuciones
def start_run(conn: Connection, run_id: UUID, source: str, cursor_before: str | None) -> None:
    conn.execute(text("""
        INSERT INTO meta.runs (run_id, source_name, status, cursor_before)
        VALUES (:id, :src, 'running', :cur)
    """), dict(id=run_id, src=source, cur=cursor_before))


def finish_run(conn: Connection, run_id: UUID, status: str, *, extracted: int = 0, loaded: int = 0,
               cursor_after: str | None = None, schema_version: int | None = None,
               error: str | None = None) -> None:
    conn.execute(text("""
        UPDATE meta.runs SET finished_at = now(), status = :status, records_extracted = :ext,
               records_loaded = :loaded, cursor_after = :cur, schema_version = :sv, error = :err
        WHERE run_id = :id
    """), dict(id=run_id, status=status, ext=extracted, loaded=loaded, cur=cursor_after,
               sv=schema_version, err=error))


# ----------------------------------------------------------------------- estado
def get_cursor(conn: Connection, source: str) -> str | None:
    return conn.execute(text("SELECT cursor_value FROM meta.state WHERE source_name = :s"),
                        dict(s=source)).scalar_one_or_none()


def set_cursor(conn: Connection, source: str, value: str) -> None:
    conn.execute(text("""
        INSERT INTO meta.state (source_name, cursor_value) VALUES (:s, :v)
        ON CONFLICT (source_name) DO UPDATE SET cursor_value = EXCLUDED.cursor_value, updated_at = now()
    """), dict(s=source, v=value))


# ---------------------------------------------------------------------- esquema
def latest_schema(conn: Connection, source: str) -> tuple[int, dict[str, str]] | None:
    row = conn.execute(text("""
        SELECT version, columns FROM meta.schema_versions
        WHERE source_name = :s ORDER BY version DESC LIMIT 1
    """), dict(s=source)).first()
    return (row.version, row.columns) if row else None


def save_schema_version(conn: Connection, source: str, version: int, columns: dict[str, str],
                        added: Sequence[str], retyped: Sequence[str], run_id: UUID) -> None:
    conn.execute(text("""
        INSERT INTO meta.schema_versions (source_name, version, columns, added, retyped, run_id)
        VALUES (:s, :v, CAST(:c AS jsonb), :a, :r, :run)
    """), dict(s=source, v=version, c=json.dumps(columns), a=list(added), r=list(retyped), run=run_id))


# ---------------------------------------------------------- perfiles y calidad
def save_profiles(conn: Connection, run_id: UUID, source: str, rows: Iterable[dict[str, Any]]) -> None:
    rows = [{**r, "run_id": run_id, "source_name": source} for r in rows]
    if rows:
        conn.execute(text("""
            INSERT INTO meta.column_profiles (run_id, source_name, column_name, inferred_type, n, null_rate,
                   n_distinct, min_value, max_value, mean, std, p50)
            VALUES (:run_id, :source_name, :column_name, :inferred_type, :n, :null_rate, :n_distinct,
                   :min_value, :max_value, :mean, :std, :p50)
        """), rows)


def save_quality(conn: Connection, run_id: UUID, source: str, rows: Iterable[dict[str, Any]]) -> None:
    rows = [{**r, "run_id": run_id, "source_name": source} for r in rows]
    if rows:
        conn.execute(text("""
            INSERT INTO meta.quality_results (run_id, source_name, column_name, rule, severity, total,
                   failed, failure_rate, threshold, passed, detail)
            VALUES (:run_id, :source_name, :column_name, :rule, :severity, :total, :failed,
                   :failure_rate, :threshold, :passed, :detail)
        """), rows)


# ----------------------------------------------------------------------- origen
def insert_origen(conn: Connection, table: str, run_id: UUID, records: Sequence[dict[str, Any]],
                  batch_size: int = 2000) -> int:
    stmt = text(f"INSERT INTO origen.{quote_ident(table)} (_run_id, _record) VALUES (:run, CAST(:rec AS jsonb))")
    for i in range(0, len(records), batch_size):
        chunk = records[i : i + batch_size]
        conn.execute(stmt, [{"run": run_id, "rec": json.dumps(r, ensure_ascii=False)} for r in chunk])
    return len(records)


# --------------------------------------------------------------------- bitácora
CATEGORIAS_BITACORA = {"datos": "Sobre los datos", "tratamiento": "Tratamiento aplicado",
                       "limpieza": "Decisión de limpieza", "cargue": "Novedad del cargue"}


def agregar_nota(conn: Connection, tabla: str, categoria: str, texto: str, autor: str,
                 automatica: bool = False) -> int:
    return conn.execute(text("""
        INSERT INTO meta.bitacora (tabla, categoria, texto, autor, automatica)
        VALUES (:t, :c, :x, :a, :auto) RETURNING id
    """), dict(t=tabla, c=categoria, x=texto, a=autor, auto=automatica)).scalar_one()


def editar_nota(conn: Connection, nota_id: int, categoria: str, texto: str, autor: str) -> bool:
    return conn.execute(text("""
        UPDATE meta.bitacora SET categoria = :c, texto = :x, autor = :a, editada_en = now() WHERE id = :id
    """), dict(id=nota_id, c=categoria, x=texto, a=autor)).rowcount == 1


# ----------------------------------------------------------------- eliminación
def eliminar_fuente(conn: Connection, source: str) -> None:
    """Borra todo el rastro de una fuente en el catálogo (la tabla de origen la borra quien llama)."""
    for tabla in ("calidad_mintic", "quality_results", "column_profiles", "schema_versions", "state", "runs"):
        conn.execute(text(f"DELETE FROM meta.{tabla} WHERE source_name = :s"), {"s": source})
    conn.execute(text("DELETE FROM meta.bitacora WHERE tabla = :t"), {"t": f"estandarizado.{source}"})
    conn.execute(text("DELETE FROM meta.sources WHERE name = :s"), {"s": source})
