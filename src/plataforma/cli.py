"""Línea de comandos: `plataforma --help`."""
from __future__ import annotations

import json
import logging
import sys
from typing import Annotated

import typer

from .config import get_settings
from .registry.loader import RegistryError, load_registry

app = typer.Typer(help="Plataforma de datos: registro de fuentes, ingesta y catálogo.", no_args_is_help=True)


@app.callback()
def _salida_segura() -> None:
    # En Windows, con la salida redirigida (archivo, tubería, tarea programada) Python usa
    # cp1252 y caracteres como "✓" rompen el comando: se reemplazan en vez de fallar.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def _registry(only_enabled: bool = False):
    try:
        return load_registry(get_settings().sources_dir, only_enabled=only_enabled)
    except RegistryError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from None


@app.command()
def validate() -> None:
    """Valida todos los YAML de sources/ sin tocar la base de datos."""
    reg = _registry()
    for name, src in reg.items():
        estado = "activa" if src.spec.enabled else "deshabilitada"
        typer.echo(f"  ✓ {name:<28} {src.spec.type:<5} {estado}")
    typer.secho(f"{len(reg)} fuente(s) válidas", fg="green")


@app.command("list")
def list_sources() -> None:
    """Lista las fuentes con su configuración principal."""
    for name, src in _registry().items():
        s = src.spec
        inc = s.incremental.cursor_field if s.incremental else "snapshot"
        typer.echo(f"{name:<28} {s.type:<5} incremental={inc:<28} tags={','.join(s.tags)}")


@app.command()
def inspect(name: str, n: Annotated[int, typer.Option("--n", "-n", help="Registros a mostrar")] = 2) -> None:
    """Trae una muestra pequeña de la fuente para ver nombres y formatos reales de los campos."""
    import pandas as pd

    from .ingestion.engine import make_extractor
    from .quality.profiling import infer_schema

    reg = _registry()
    if name not in reg:
        typer.secho(f"fuente desconocida: {name}", fg="red", err=True)
        raise typer.Exit(1)
    spec = reg[name].spec.model_copy(update={"max_records": max(n, 50)})
    if spec.type == "rest" and hasattr(spec.pagination, "page_size"):
        spec = spec.model_copy(update={"pagination": spec.pagination.model_copy(update={"page_size": max(n, 50)})})
    try:
        page = next(iter(make_extractor(spec, None).pages()), [])
    except Exception as e:  # noqa: BLE001
        typer.secho(f"no se pudo leer la fuente: {type(e).__name__}: {e}", fg="red", err=True)
        raise typer.Exit(1) from None
    if not page:
        typer.echo("la fuente no devolvió registros")
        return
    typer.echo(json.dumps(page[:n], indent=2, ensure_ascii=False))
    typer.secho("\nTipos inferidos en la muestra:", bold=True)
    for col, typ in infer_schema(pd.DataFrame.from_records(page)).items():
        typer.echo(f"  {col:<40} {typ}")


@app.command("dbt-sources")
def dbt_sources(
    out: Annotated[str, typer.Option(help="Archivo de salida")] = "transform/models/_fuentes.yml",
) -> None:
    """Genera las declaraciones `source()` de dbt a partir del registro: cada YAML nuevo
    queda disponible en dbt sin escribirlo a mano."""
    from pathlib import Path

    import yaml

    origen = []
    for name, src in _registry().items():
        s = src.spec
        origen.append({
            "name": name,
            "description": s.description,
            "meta": {"tipo": s.type, "llave": s.primary_key, "tags": s.tags,
                     "incremental": s.incremental.cursor_field if s.incremental else None},
            "columns": [{"name": "_record", "description": "Registro crudo (jsonb)"}],
        })
    doc = {
        "version": 2,
        "sources": [
            {"name": "origen", "schema": "origen",
             "description": "Generado por `plataforma dbt-sources`. No editar a mano.", "tables": origen},
            {"name": "meta", "schema": "meta", "description": "Catálogo de la plataforma",
             "tables": [{"name": t} for t in
                        ("sources", "runs", "state", "schema_versions", "column_profiles", "quality_results")]},
        ],
    }
    Path(out).write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    typer.secho(f"{len(origen)} fuente(s) escritas en {out}", fg="green")


@app.command("init-db")
def init_db() -> None:
    """Crea los esquemas origen/estandarizado/analitico/meta y las tablas del catálogo."""
    from .storage.db import bootstrap, get_engine

    bootstrap(get_engine())
    typer.secho("base de datos lista", fg="green")


@app.command("crear-lector")
def crear_lector(
    usuario: Annotated[str, typer.Argument(help="Nombre del usuario: minúsculas, números y guion bajo")],
    clave: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True,
                                       help="Contraseña; si se omite, se pide sin mostrarla")],
) -> None:
    """Crea (o actualiza) un usuario de PostgreSQL de solo lectura sobre las capas estandarizada y
    analítica y el catálogo, para consultar desde R, Python o el servidor MCP. No ve la capa de
    origen, que incluye las cargas en cuarentena."""
    from psycopg import sql
    from sqlalchemy import text

    from .registry.models import SLUG
    from .storage.db import bootstrap, get_engine

    if not SLUG.match(usuario):
        typer.secho("usuario inválido: usa minúsculas, números y guion bajo", fg="red", err=True)
        raise typer.Exit(1)
    engine = get_engine()
    bootstrap(engine)
    rol, esquemas = sql.Identifier(usuario), sql.SQL(", ").join(
        sql.Identifier(s) for s in ("estandarizado", "analitico", "meta"))
    with engine.begin() as conn:
        existe = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": usuario}).first()
        # composición de psycopg: el nombre y la clave van escapados, nunca interpolados como texto
        raw = conn.connection.driver_connection
        accion = "ALTER ROLE {} WITH LOGIN PASSWORD {}" if existe else "CREATE ROLE {} WITH LOGIN PASSWORD {}"
        raw.execute(sql.SQL(accion).format(rol, sql.Literal(clave)))
        raw.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(esquemas, rol))
        raw.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(esquemas, rol))
        # las tablas que dbt cree después también quedan legibles
        raw.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(esquemas, rol))
    typer.secho(f"usuario '{usuario}' {'actualizado' if existe else 'creado'} con acceso de solo lectura", fg="green")


@app.command()
def ingest(
    name: Annotated[str | None, typer.Argument(help="Fuente a cargar; omitir con --all")] = None,
    all_: Annotated[bool, typer.Option("--all", help="Cargar todas las fuentes activas")] = False,
    full_refresh: Annotated[bool, typer.Option(help="Ignorar el cursor guardado")] = False,
    verbose: Annotated[bool, typer.Option("-v")] = False,
) -> None:
    """Ejecuta la ingesta de una fuente o de todas las activas."""
    from .ingestion.engine import run_source
    from .storage.db import bootstrap, get_engine

    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s")
    reg = _registry(only_enabled=all_)
    if all_:
        targets = list(reg.values())
    elif name in reg:
        targets = [reg[name]]
    else:
        typer.secho("indica una fuente válida o usa --all", fg="red", err=True)
        raise typer.Exit(1)

    engine = get_engine()
    bootstrap(engine)
    failed = False
    for src in targets:
        r = run_source(engine, src.spec, full_refresh=full_refresh)
        color = {"success": "green", "success_with_warnings": "yellow"}.get(r.status, "red")
        typer.secho(f"{r.source:<28} {r.status:<22} extraídos={r.extracted:<7} cargados={r.loaded:<7} "
                    f"cursor={r.cursor_after}", fg=color)
        if r.schema_changes.get("added") or r.schema_changes.get("retyped"):
            typer.echo(f"    esquema v{r.schema_version}: {r.schema_changes}")
        if r.failed_checks:
            typer.echo(f"    reglas incumplidas: {', '.join(r.failed_checks)}")
        if r.error:
            typer.echo(f"    error: {r.error}")
        failed |= r.status == "failed"
    raise typer.Exit(1 if failed else 0)


if __name__ == "__main__":
    app()
