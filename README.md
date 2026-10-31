# Plataforma de datos (opción B: centrada en PostgreSQL)

Plataforma de uso general para extraer, validar, versionar y servir datos. No
está atada a un proyecto: **cada fuente nueva es un archivo YAML**, y el motor
de ingesta, el catálogo, dbt y la API la descubren solos. Con cada carga la
plataforma acumula contexto: esquemas versionados, perfiles estadísticos por
columna, resultados de calidad e historial de ejecuciones.

```
sources/*.yml ──► motor de ingesta ──► bronze.<fuente>  (jsonb, solo se agrega)
                        │                     │
                        ▼                     ▼  dbt
                  meta.* (catálogo)    silver.* ──► gold.*
                        │                                │
                        └──────────► API FastAPI ◄───────┘
```

## Inicio rápido

```bash
cp .env.example .env
docker compose up -d --build db api          # Postgres + API en http://localhost:8000/docs
docker compose run --rm cli validate         # valida el registro de fuentes
docker compose run --rm cli inspect secop_procesos   # muestra y tipos reales de los campos
docker compose run --rm cli ingest --all     # carga todas las fuentes activas
docker compose run --rm cli dbt-sources      # declara en dbt las tablas de bronce
docker compose run --rm dbt build            # construye y prueba plata y oro
```

Sin Docker: `pip install -e ".[dev,transform]"` y usa el comando `plataforma`
directamente (ver `Makefile`).

## Estructura

```
plataforma-datos/
├── sources/                    # REGISTRO DE FUENTES: un YAML por fuente
│   ├── _plantilla.yml          # referencia completa del formato (no se carga)
│   ├── secop_procesos.yml      # API Socrata de datos.gov.co, incremental
│   └── ejemplo_archivo.yml     # fuente tipo archivo (deshabilitada)
├── src/plataforma/
│   ├── registry/               # modelo pydantic del YAML + cargador con ${VARIABLES}
│   ├── ingestion/              # extractores REST y archivo, motor genérico
│   ├── quality/                # inferencia de tipos, perfilado y contratos
│   ├── storage/                # DDL del catálogo, escritura en meta.* y bronze.*
│   ├── api/                    # FastAPI genérica: catálogo + datasets
│   └── cli.py                  # validate · list · inspect · ingest · dbt-sources · init-db
├── transform/                  # proyecto dbt (silver y gold)
│   ├── macros/plataforma.sql   # bronce_vigente(), a_numero(), a_fecha()
│   └── models/{silver,gold}/
├── tests/                      # unitarias + integración contra Postgres
├── docker-compose.yml · Dockerfile · Makefile · pyproject.toml
└── data/landing/               # zona de aterrizaje para fuentes tipo archivo
```

## Formato del YAML de fuentes

La referencia comentada completa está en [`sources/_plantilla.yml`](sources/_plantilla.yml).

| Bloque | Obligatorio | Para qué sirve |
|---|---|---|
| `name`, `description` | sí | Identidad. `name` = nombre del archivo = tabla `bronze.<name>` |
| `type` | sí | `rest` o `file` |
| `connection` | sí | REST: `base_url`, `auth`, `params`, `records_path`… · File: `path`, `format`, `options` |
| `pagination` | no | `none`, `offset`, `page` o `cursor` (solo REST) |
| `incremental` | no | Campo cursor, valor inicial y filtro opcional que se empuja a la API |
| `primary_key` | no | Llave natural; dbt la usa para quedarse con la versión vigente |
| `contract` | no | Columnas obligatorias, reglas de calidad y política ante cambios de esquema |
| `tags`, `owner`, `schedule`, `enabled`, `max_records` | no | Metadatos y límites operativos |

Reglas de contrato disponibles: `not_null`, `unique`, `non_negative`, `range`,
`in_set`, `regex`. Cada una tiene `severity` (`warn` | `error`) y
`max_failure_rate` (tolerancia como fracción de filas).

Los secretos nunca van en el YAML: se escriben como `${VARIABLE}` o
`${VARIABLE:-defecto}` y se leen del entorno. En el catálogo se guardan
enmascarados (`***`).

## Qué hace cada ejecución

1. Registra o actualiza la fuente en `meta.sources` (con hash del YAML).
2. Lee el cursor de `meta.state` y extrae solo lo nuevo.
3. Infiere tipos (las APIs abiertas devuelven números y fechas como texto) y,
   si aparecen columnas o cambian tipos, crea una versión en `meta.schema_versions`.
4. Evalúa el contrato (`meta.quality_results`) y perfila cada columna
   (`meta.column_profiles`: nulos, distintos, min, max, media, desviación, mediana).
5. Agrega los registros crudos a `bronze.<fuente>` y avanza el cursor.

Los pasos 3–5 van en una sola transacción. Estados posibles de una ejecución:

| Estado | Significado | ¿Llega a plata? |
|---|---|---|
| `success` | Todo bien | sí |
| `success_with_warnings` | Falló alguna regla `warn` | sí |
| `failed_quality` | Falló una regla `error`: los datos quedan en bronce como evidencia | **no** (cuarentena) |
| `failed` | Error de extracción, columnas obligatorias ausentes o cambio de esquema prohibido | no se cargó nada |

## API

| Endpoint | Devuelve |
|---|---|
| `GET /sources?tag=` | Fuentes con último estado, cursor y versión de esquema |
| `GET /sources/{name}` | YAML (sin secretos), esquema vigente y último perfil |
| `GET /sources/{name}/schema-history` | Evolución del esquema |
| `GET /sources/{name}/runs` | Historial de ejecuciones |
| `GET /sources/{name}/profile-history/{column}` | Serie del perfil de una columna (para detectar derivas) |
| `GET /runs/{run_id}/quality` | Resultado de cada regla en una carga |
| `GET /datasets?layer=` | Tablas disponibles en silver y gold |
| `GET /datasets/{layer}/{name}?limit&offset&order_by=-col` | Datos paginados |

## Agregar una fuente nueva

1. Copia `sources/_plantilla.yml` como `sources/<nombre>.yml` y ajústalo.
2. `plataforma validate` y `plataforma inspect <nombre>` para ver los campos reales.
3. `plataforma ingest <nombre>`.
4. `plataforma dbt-sources` y crea su modelo en `transform/models/silver/`
   usando la macro `bronce_vigente('<nombre>', ['<llave>'])`.

## Pruebas

```bash
pytest -q                                         # unitarias
PLATAFORMA_TEST_DATABASE_URL=postgresql+psycopg://plataforma:plataforma@localhost:5432/plataforma_test pytest -q
```

La prueba de integración simula una API, hace tres cargas incrementales
(incluye un cambio de esquema y una regla en cuarentena), verifica que el
catálogo no guarde secretos y recorre todos los endpoints.

## Próximos pasos

- Orquestador (Dagster o Airflow) leyendo `schedule` de cada YAML.
- Detección de derivas sobre `meta.column_profiles`: PSI y pruebas de
  Kolmogorov-Smirnov entre cargas, gráficos de control para tasas de nulos.
- Tablero de `gold.salud_fuentes`.
- Migración del almacenamiento a Parquet/Iceberg en MinIO (opción C) sin
  tocar el registro, la ingesta ni la API.
# consultoria_project
