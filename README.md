# plataforma-datos

Plataforma abierta para extraer, validar, versionar y servir datos públicos y
propios. **Cada fuente nueva es un archivo YAML**: el motor de ingesta, el
catálogo, dbt y la API la descubren solos. Con cada carga la plataforma acumula
contexto sobre sus datos: esquemas versionados, perfiles estadísticos por
columna, resultados de calidad e historial de ejecuciones.

Se desarrolla inicialmente para la **Facultad de Estadística de la Universidad
Santo Tomás**. Está pensada para replicarse después en otras facultades y
entidades. La fuente piloto son los procesos de contratación pública de
[SECOP II](https://www.datos.gov.co/Gastos-Gubernamentales/SECOP-II-Procesos-de-Contrataci-n/p6dx-8zbt)
publicados en datos.gov.co.

## Para qué sirve

| Quién | Qué obtiene |
| --- | --- |
| Estudiantes | Datos reales ya depurados para cursos y trabajos de grado, y práctica con el ciclo completo del dato |
| Docentes | Conjuntos de datos comunes, estables y documentados para clases y evaluaciones |
| Investigación | Series históricas versionadas y trazables, para análisis reproducibles |
| Institución | Base para un observatorio de datos públicos, con software libre y sin costos de licencia |

## Cómo funciona

```text
sources/*.yml ──► motor de ingesta ──► origen.<fuente>   (jsonb, solo se agrega)
                        │                     │
                        ▼                     ▼  dbt
                  meta.* (catálogo)    estandarizado.* ──► analitico.*
                        │                                      │
                        └─────────────► API FastAPI ◄──────────┘
                                         servidor MCP
```

| Capa | Esquema | Qué contiene | Quién la escribe |
| --- | --- | --- | --- |
| Origen | `origen` | El dato tal como llega de la fuente, sin tocar. Solo se agrega; nunca se borra. | Motor de ingesta |
| Estandarizado | `estandarizado` | Dato depurado: tipos correctos, sin duplicados y sin cargas en cuarentena. | dbt |
| Analítico | `analitico` | Tablas agregadas y modeladas para reportes y tableros. | dbt |

Estas capas equivalen a las que la industria llama *bronze*, *silver* y *gold*
(arquitectura medallion). Una base creada con los nombres antiguos se migra sola
la próxima vez que se ejecuta `plataforma init-db` o `ingest`, o cuando arranca la API.

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS o Linux), o
- Python 3.11 o superior y PostgreSQL 16, para ejecutar sin Docker.

## Inicio rápido

```bash
git clone https://github.com/aviladaniel19/consultoria_project.git
cd consultoria_project
cp .env.example .env            # en Windows: copy .env.example .env
```

**Windows:** doble clic en `iniciar.bat`. Abre Docker Desktop si hace falta,
levanta PostgreSQL y la API, y espera a que respondan. Luego abre
<http://localhost:8000> en el navegador.

**macOS / Linux:**

```bash
docker compose up -d --build db api          # PostgreSQL + plataforma web en http://localhost:8000
```

Primera carga de datos (cualquier sistema):

```bash
docker compose run --rm cli validate                  # valida el registro de fuentes
docker compose run --rm cli inspect secop_procesos    # muestra los campos reales de la fuente
docker compose run --rm cli ingest --all              # carga todas las fuentes activas
docker compose run --rm cli dbt-sources               # declara en dbt las tablas de origen
docker compose run --rm dbt build                     # construye y prueba estandarizado y analitico
```

Para detener: `docker compose down`. Los datos se conservan en el volumen `pgdata`.

Sin Docker: `pip install -e ".[dev,transform]"` y usa el comando `plataforma`
directamente. El `Makefile` resume los comandos, pero usa sintaxis POSIX: en
Windows funciona desde Git Bash.

## Configuración

Toda la configuración va en `.env`, que no se sube al repositorio. La plantilla
es [`.env.example`](.env.example).

| Variable | Para qué sirve |
| --- | --- |
| `POSTGRES_PASSWORD` | Contraseña de PostgreSQL en Docker |
| `PLATAFORMA_DATABASE_URL` | Conexión a la base cuando se ejecuta fuera de Docker |
| `PLATAFORMA_API_KEYS` | Claves de acceso a la API, separadas por coma. Vacío = API abierta (solo desarrollo) |
| `PLATAFORMA_CORS_ORIGINS` | Sitios web autorizados a llamar la API desde el navegador |
| `PLATAFORMA_MCP_DATABASE_URL` | Usuario de solo lectura para el servidor MCP |
| `SOCRATA_APP_TOKEN` | Token opcional de datos.gov.co; sube el límite de peticiones |
| `GROQ_API_KEY` | Reservada para el asistente «Pregúntale a los datos» (próxima versión; aún no se usa) |
| `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` | Reservadas como alternativas de modelo para el asistente (aún no se usan) |

Los secretos nunca van en los YAML ni en el código: los YAML los referencian
como `${VARIABLE}` y en el catálogo se guardan enmascarados (`***`).

## Uso

### Plataforma web

En <http://localhost:8000> hay una interfaz para quienes no programan:

| Sección | Para qué sirve |
| --- | --- |
| **Catálogo** | Buscar datasets por tema, columna o fuente (sin importar tildes), con su tamaño, fecha de actualización y estado de calidad |
| **Ficha del dataset** | Vista previa, perfil estadístico de cada columna (vacíos, distintos, media, mediana, histograma), historial de cargas y reglas de calidad, y código listo para R, Python y SQL |
| **Explorar** | Filtrar, ordenar y paginar cualquier tabla, y descargar exactamente esas filas en CSV (o CSV para Excel, con `;` y decimales con coma) |
| **Salud** | Estado de cada fuente: última carga, historial reciente y reglas incumplidas |

El buscador superior (atajo `Ctrl+K`) salta a cualquier dataset, columna o
fuente. Tiene tema claro y oscuro con los colores institucionales, y en el
celular las secciones pasan a una barra inferior. Si `PLATAFORMA_API_KEYS` tiene
claves, la interfaz pide una al entrar y la recuerda en el navegador.

Las páginas se generan en el servidor con plantillas Jinja y HTMX
(`src/plataforma/web/`): no hay paso de compilación ni dependencias de
JavaScript que instalar, y funciona sin internet.

### Línea de comandos

| Comando | Qué hace |
| --- | --- |
| `plataforma validate` | Valida todos los YAML de `sources/` sin tocar la base |
| `plataforma list` | Lista las fuentes y su configuración principal |
| `plataforma inspect <fuente>` | Trae una muestra para ver nombres y tipos reales de los campos |
| `plataforma ingest <fuente>` o `--all` | Ejecuta la carga; `--full-refresh` ignora el cursor guardado |
| `plataforma dbt-sources` | Genera las fuentes de dbt a partir del registro |
| `plataforma init-db` | Crea los esquemas y el catálogo |
| `plataforma crear-lector <usuario>` | Crea un usuario de PostgreSQL de solo lectura |

### API

Documentación interactiva en <http://localhost:8000/docs>.

| Endpoint | Devuelve |
| --- | --- |
| `GET /health` | Estado del servicio (público) |
| `GET /sources?tag=` | Fuentes con último estado, cursor y versión de esquema |
| `GET /sources/{name}` | YAML (sin secretos), esquema vigente y último perfil |
| `GET /sources/{name}/schema-history` | Evolución del esquema |
| `GET /sources/{name}/runs` | Historial de ejecuciones |
| `GET /sources/{name}/profile-history/{column}` | Serie del perfil de una columna (para detectar derivas) |
| `GET /runs/{run_id}/quality` | Resultado de cada regla en una carga |
| `GET /datasets?layer=` | Tablas disponibles en estandarizado y analitico |
| `GET /datasets/{layer}/{name}?limit&offset&order_by=-col&filtro=` | Datos paginados y filtrados |
| `GET /datasets/{layer}/{name}/csv?filtro=&order_by=&sep=` | Descarga en CSV (`sep=;` para Excel) |

`filtro` se repite y tiene el formato `columna:operador:valor`, con operador
`eq`, `ne`, `contiene`, `gt`, `ge`, `lt`, `le`, `vacio` o `no_vacio`. Por
ejemplo: `?filtro=departamento:eq:Antioquia&filtro=precio_base:ge:1000000`.

Todos los endpoints salvo `/health` piden la cabecera `X-API-Key` con una de las
claves de `PLATAFORMA_API_KEYS`:

```bash
curl -H "X-API-Key: <clave>" http://localhost:8000/datasets
```

### Usuarios de solo lectura (R, Python)

```bash
plataforma crear-lector estudiantes      # pide la contraseña sin mostrarla
```

El usuario puede leer las capas `estandarizado` y `analitico` y el catálogo
`meta`. No puede escribir ni ver la capa `origen`, que incluye las cargas en
cuarentena. Las tablas que dbt cree después también le quedan legibles. Desde R:

```r
library(DBI)
con <- dbConnect(RPostgres::Postgres(), host = "localhost", dbname = "plataforma",
                 user = "estudiantes", password = Sys.getenv("CLAVE_PLATAFORMA"))
dbGetQuery(con, "SELECT * FROM analitico.contratacion_mensual LIMIT 10")
```

### Servidor MCP (asistentes de IA)

`plataforma-mcp` permite que un asistente como Claude consulte la plataforma en
lenguaje natural. Ofrece seis herramientas de solo lectura: `listar_fuentes`,
`describir_fuente`, `listar_datasets`, `describir_dataset`, `consultar_dataset`
y `consulta_sql`. Esta última acepta una sola consulta SELECT, corre en una
transacción de solo lectura con límite de 30 segundos y devuelve hasta 500 filas.

```bash
pip install -e ".[mcp]"
plataforma crear-lector asistente
```

En Claude Desktop, agrega a `claude_desktop_config.json` (en Windows está en
`%APPDATA%\Claude\`):

```json
{
  "mcpServers": {
    "plataforma-datos": {
      "command": "C:\\ruta\\al\\proyecto\\.venv\\Scripts\\plataforma-mcp.exe",
      "env": {
        "PLATAFORMA_MCP_DATABASE_URL": "postgresql+psycopg://asistente:<clave>@localhost:5432/plataforma"
      }
    }
  }
}
```

En Claude Code:
`claude mcp add plataforma-datos -e PLATAFORMA_MCP_DATABASE_URL=... -- <ruta>/plataforma-mcp`

Usa siempre un usuario de `crear-lector`. Con el usuario principal, la
transacción de solo lectura impide escribir, pero ese usuario conserva otros
privilegios de administrador.

## Fuentes de datos

### Formato del YAML

La referencia comentada completa está en [`sources/_plantilla.yml`](sources/_plantilla.yml).

| Bloque | Obligatorio | Para qué sirve |
| --- | --- | --- |
| `name`, `description` | sí | Identidad. `name` = nombre del archivo = tabla `origen.<name>` |
| `type` | sí | `rest` o `file` |
| `connection` | sí | REST: `base_url`, `auth`, `params`, `records_path`… · File: `path`, `format`, `options` |
| `pagination` | no | `none`, `offset`, `page` o `cursor` (solo REST) |
| `incremental` | no | Campo cursor, valor inicial y filtro opcional que se envía a la API |
| `primary_key` | no | Llave natural; dbt la usa para quedarse con la versión vigente |
| `contract` | no | Columnas obligatorias, reglas de calidad y política ante cambios de esquema |
| `tags`, `owner`, `schedule`, `enabled`, `max_records` | no | Metadatos y límites operativos |

Reglas de contrato disponibles: `not_null`, `unique`, `non_negative`, `range`,
`in_set` y `regex`. Cada una tiene `severity` (`warn` o `error`) y
`max_failure_rate` (tolerancia como fracción de filas).

Tipos de fuente soportados: APIs REST que devuelven JSON (cuatro tipos de
paginación y de autenticación) y archivos CSV, Excel, Parquet o JSON, locales o
por URL. La lectura directa desde otras bases de datos aún no está disponible.

### Agregar una fuente nueva

1. Copia `sources/_plantilla.yml` como `sources/<nombre>.yml` y ajústalo.
2. `plataforma validate` y `plataforma inspect <nombre>` para ver los campos reales.
3. `plataforma ingest <nombre>`.
4. `plataforma dbt-sources` y crea su modelo en `transform/models/estandarizado/`
   usando la macro `origen_vigente('<nombre>', ['<llave>'])`.

### Qué hace cada ejecución

1. Registra o actualiza la fuente en `meta.sources` (con hash del YAML).
2. Lee el cursor de `meta.state` y extrae solo lo nuevo. Si `max_records` corta
   la carga a mitad de un grupo de valores, el cursor no avanza sobre ese grupo
   y se vuelve a pedir completo en la siguiente ejecución.
3. Infiere tipos (las APIs abiertas devuelven números y fechas como texto) y,
   si aparecen columnas o cambian tipos, crea una versión en `meta.schema_versions`.
4. Evalúa el contrato (`meta.quality_results`) y perfila cada columna
   (`meta.column_profiles`: nulos, distintos, mínimo, máximo, media, desviación, mediana).
5. Agrega los registros crudos a `origen.<fuente>` y avanza el cursor.

Los pasos 3 a 5 van en una sola transacción. Estados posibles de una ejecución:

| Estado | Significado | ¿Llega a estandarizado? |
| --- | --- | --- |
| `success` | Todo bien | sí |
| `success_with_warnings` | Falló alguna regla `warn` | sí |
| `failed_quality` | Falló una regla `error`: los datos quedan en origen como evidencia | **no** (cuarentena) |
| `failed` | Error de extracción, columnas obligatorias ausentes o cambio de esquema prohibido | no se cargó nada |

## Estructura del repositorio

```text
.
├── sources/                    # REGISTRO DE FUENTES: un YAML por fuente
│   ├── _plantilla.yml          # referencia completa del formato (no se carga)
│   ├── secop_procesos.yml      # API Socrata de datos.gov.co, incremental
│   └── ejemplo_archivo.yml     # fuente tipo archivo (deshabilitada)
├── src/plataforma/
│   ├── registry/               # modelo pydantic del YAML + cargador con ${VARIABLES}
│   ├── ingestion/              # extractores REST y archivo, motor genérico
│   ├── quality/                # inferencia de tipos, perfilado y contratos
│   ├── storage/                # DDL del catálogo, escritura en meta.* y origen.*
│   ├── api/                    # FastAPI genérica: catálogo + datasets, con clave de acceso
│   ├── web/                    # plataforma web: rutas, plantillas Jinja, estilos, HTMX y fuentes
│   ├── consultas.py            # lectura, filtros y CSV compartidos por API, web y MCP
│   ├── mcp_server.py           # servidor MCP de solo lectura para asistentes de IA
│   └── cli.py                  # comando `plataforma`
├── transform/                  # proyecto dbt (estandarizado y analitico)
│   ├── macros/plataforma.sql   # origen_vigente(), a_numero(), a_fecha()
│   └── models/{estandarizado,analitico}/
├── tests/                      # unitarias + integración contra PostgreSQL
├── data/landing/               # zona de aterrizaje para fuentes tipo archivo
├── iniciar.bat                 # arranque en Windows
├── informe-revision.html       # informe de la revisión técnica
├── objetivos-estado-del-arte.html  # objetivos, beneficiarios y estado del arte
└── docker-compose.yml · Dockerfile · Makefile · pyproject.toml
```

## Desarrollo y pruebas

```bash
python -m venv .venv
.venv/Scripts/activate                            # macOS / Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                                         # pruebas unitarias
ruff check src tests                              # estilo
```

Las pruebas de integración necesitan un PostgreSQL vacío. Se borran y recrean
sus esquemas, así que nunca apuntes esta variable a la base real:

```bash
PLATAFORMA_TEST_DATABASE_URL=postgresql+psycopg://plataforma:plataforma@localhost:5432/plataforma_test pytest -q
```

La prueba de integración simula una API y hace tres cargas incrementales, que
incluyen un cambio de esquema y una regla en cuarentena. También verifica que el
catálogo no guarde secretos, recorre todos los endpoints, comprueba la clave de
la API y los permisos del usuario de solo lectura, prueba las herramientas MCP
y recorre la plataforma web: catálogo, fichas, filtros, descargas e ingreso con clave.

## Hoja de ruta

- Asistente «Pregúntale a los datos» en la web, con Groq como modelo de pruebas.
- Agregar fuentes desde el navegador, con un asistente paso a paso que genere el YAML.
- Lanzar cargas desde la sección Salud, con permisos de administrador.
- Cargas automáticas con un orquestador (Dagster o Airflow) que lea `schedule` de cada YAML.
- Límites de uso por clave en la API.
- Detección de derivas sobre `meta.column_profiles`: PSI y pruebas de
  Kolmogorov-Smirnov entre cargas, gráficos de control para tasas de nulos.
- Conector para leer otras bases de datos, con anonimización de datos personales.
- Migración del almacenamiento a Parquet/Iceberg sin tocar el registro, la ingesta ni la API.

## Licencia

Pendiente de definir con la Universidad Santo Tomás. Hasta entonces, el código
no tiene una licencia de uso abierta.
