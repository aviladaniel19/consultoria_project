-- Esquemas por capa. Idempotente: se puede ejecutar en cada arranque.

-- Migración v0.1: las capas se llamaban bronze/silver/gold. Si una base antigua
-- aún tiene esos esquemas (y no los nuevos), se renombran conservando los datos.
DO $$
DECLARE par text[];
BEGIN
    FOREACH par SLICE 1 IN ARRAY ARRAY[['bronze','origen'], ['silver','estandarizado'], ['gold','analitico']] LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = par[1])
           AND NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = par[2]) THEN
            -- quote_ident en vez de format(): el driver trata el signo de porcentaje como marcador de parámetro
            -- (por eso este archivo no debe contener ese signo, ni siquiera en comentarios)
            EXECUTE 'ALTER SCHEMA ' || quote_ident(par[1]) || ' RENAME TO ' || quote_ident(par[2]);
        END IF;
    END LOOP;
END $$;

CREATE SCHEMA IF NOT EXISTS origen;         -- dato tal como llega de la fuente, solo se agrega, una tabla por fuente
CREATE SCHEMA IF NOT EXISTS estandarizado;  -- depurado, tipado y sin duplicados (dbt)
CREATE SCHEMA IF NOT EXISTS analitico;      -- agregado y modelado para reportes (dbt)
CREATE SCHEMA IF NOT EXISTS meta;           -- catálogo: el "contexto" que la plataforma acumula

-- Fuentes registradas: espejo del YAML en la base, con historial por hash
CREATE TABLE IF NOT EXISTS meta.sources (
    name          text PRIMARY KEY,
    description   text NOT NULL,
    owner         text,
    tags          text[] NOT NULL DEFAULT '{}',
    type          text NOT NULL,
    enabled       boolean NOT NULL DEFAULT true,
    spec          jsonb NOT NULL,
    spec_hash     text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Cada ejecución de ingesta
CREATE TABLE IF NOT EXISTS meta.runs (
    run_id             uuid PRIMARY KEY,
    source_name        text NOT NULL REFERENCES meta.sources(name),
    started_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz,
    status             text NOT NULL CHECK (status IN
                         ('running','success','success_with_warnings','failed_quality','failed')),
    records_extracted  integer NOT NULL DEFAULT 0,
    records_loaded     integer NOT NULL DEFAULT 0,
    cursor_before      text,
    cursor_after       text,
    schema_version     integer,
    error              text
);
CREATE INDEX IF NOT EXISTS runs_source_idx ON meta.runs (source_name, started_at DESC);

-- Último cursor incremental confirmado por fuente
CREATE TABLE IF NOT EXISTS meta.state (
    source_name  text PRIMARY KEY REFERENCES meta.sources(name),
    cursor_value text NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Versiones del esquema observado. Es acumulativo: se crea una versión nueva
-- cuando aparecen columnas o cambia un tipo. Que una columna falte en un lote
-- no cuenta como eliminación (muchas APIs omiten las llaves con valor nulo).
CREATE TABLE IF NOT EXISTS meta.schema_versions (
    source_name text NOT NULL REFERENCES meta.sources(name),
    version     integer NOT NULL,
    columns     jsonb NOT NULL,          -- {"columna": "tipo_inferido", ...}
    added       text[] NOT NULL DEFAULT '{}',
    retyped     text[] NOT NULL DEFAULT '{}',
    run_id      uuid NOT NULL,
    detected_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_name, version)
);

-- Perfil estadístico de cada columna en cada carga (línea base para detectar derivas)
CREATE TABLE IF NOT EXISTS meta.column_profiles (
    run_id        uuid NOT NULL REFERENCES meta.runs(run_id),
    source_name   text NOT NULL,
    column_name   text NOT NULL,
    inferred_type text NOT NULL,
    n             integer NOT NULL,
    null_rate     double precision NOT NULL,
    n_distinct    integer NOT NULL,
    min_value     text,
    max_value     text,
    mean          double precision,
    std           double precision,
    p50           double precision,
    PRIMARY KEY (run_id, column_name)
);

-- Resultado de cada regla del contrato en cada carga
CREATE TABLE IF NOT EXISTS meta.quality_results (
    run_id       uuid NOT NULL REFERENCES meta.runs(run_id),
    source_name  text NOT NULL,
    column_name  text NOT NULL,
    rule         text NOT NULL,
    severity     text NOT NULL,
    total        integer NOT NULL,
    failed       integer NOT NULL,
    failure_rate double precision NOT NULL,
    threshold    double precision NOT NULL,
    passed       boolean NOT NULL,
    detail       text
);
CREATE INDEX IF NOT EXISTS quality_run_idx ON meta.quality_results (run_id);

-- Última vez que dbt reconstruyó cada tabla de estandarizado y analitico.
-- La escribe un post-hook de dbt (dbt_project.yml); el frontend la muestra como "actualizado".
CREATE TABLE IF NOT EXISTS meta.construcciones (
    tabla         text PRIMARY KEY,                 -- esquema.tabla
    construida_en timestamptz NOT NULL DEFAULT now()
);
