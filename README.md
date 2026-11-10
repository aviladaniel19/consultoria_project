# plataforma-datos

Plataforma abierta para extraer, validar, versionar y servir datos públicos y
propios. Desde la web se sube un archivo o se conecta una API, se revisan las
columnas y se publica: en segundos el dataset queda en el catálogo, listo para
explorar, descargar y usar desde R o Python. Con cada carga la plataforma acumula
contexto sobre sus datos: esquemas versionados, perfiles estadísticos por
columna, resultados de calidad e historial de ejecuciones. Cada carga se evalúa
además con los lineamientos de calidad de MinTIC para datos abiertos, antes y
después de la limpieza.

Se desarrolla inicialmente para la **Facultad de Estadística de la Universidad
Santo Tomás**. Está pensada para replicarse después en otras facultades y
entidades.

## Para qué sirve

| Quién | Qué obtiene |
| --- | --- |
| Estudiantes | Datos reales ya depurados para cursos y trabajos de grado, y práctica con el ciclo completo del dato |
| Docentes | Conjuntos de datos comunes, estables y documentados para clases y evaluaciones |
| Investigación | Series históricas versionadas y trazables, para análisis reproducibles |
| Institución | Base para un observatorio de datos públicos, con software libre y sin costos de licencia |

## Cómo funciona

```text
web o sources/*.yml ──► motor de ingesta ──► origen.<fuente>   (jsonb, solo se agrega)
                              │                     │  publicación automática o dbt
                              ▼                     ▼
                        meta.* (catálogo)    estandarizado.* ──► analitico.* (dbt)
                              │                                      │
                              └──────── web · API · servidor MCP ◄───┘
```

| Capa | Esquema | Qué contiene | Quién la escribe |
| --- | --- | --- | --- |
| Origen | `origen` | El dato tal como llega de la fuente, sin tocar. Solo se agrega; nunca se borra. | Motor de ingesta |
| Estandarizado | `estandarizado` | Dato depurado: tipos correctos, sin duplicados y sin cargas en cuarentena. | Publicación automática tras cada carga, o un modelo dbt curado |
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
actualiza la imagen si el código cambió, levanta PostgreSQL y la plataforma web,
y espera a que respondan.

**macOS / Linux:**

```bash
docker compose up -d --build db api          # PostgreSQL + plataforma web en http://localhost:8000
```

**Primera carga:** abre <http://localhost:8000/cargar>, sube un archivo o conecta
una API, revisa las columnas y pulsa **Publicar dataset**. Para probar hay datos
pequeños en [`ejemplos/`](ejemplos/README.md): el conjunto Iris en CSV, en CSV de
Excel colombiano y en Excel, y la API de municipios DIVIPOLA del DANE.

Para detener: `docker compose down`. Los datos se conservan en el volumen
`pgdata`; `docker compose down -v` los borra y deja la plataforma como nueva.

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
| `PLATAFORMA_API_KEYS` | Claves de lectura (API y web), separadas por coma. Vacío = abierta (solo desarrollo) |
| `PLATAFORMA_ADMIN_KEYS` | Claves que además permiten cargar, actualizar y eliminar datos desde la web |
| `PLATAFORMA_MAX_SUBIDA_MB` | Tamaño máximo de un archivo subido (200 MB por defecto) |
| `PLATAFORMA_CALIDAD_MAX_FILAS` | Filas que lee la evaluación de calidad MinTIC; por encima usa una muestra aleatoria (200.000 por defecto) |
| `PLATAFORMA_PERMITIR_REDES_PRIVADAS` | `true` permite conectar desde la web APIs en redes privadas (p. ej. internas de la universidad). Por defecto solo APIs públicas |
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
| **Ficha del dataset** | Seis pestañas: **Vista previa** (las columnas elegidas al cargar, con filtros), **Columnas** (perfil estadístico e histograma de cada una), **Calidad** (evaluación según MinTIC antes y después de la limpieza, historial de cargas y reglas del contrato), **Indicadores** (KPI sugeridos con su SQL), **Bitácora** (notas sobre los datos y su tratamiento) y **Cómo usarlo** (código para R, Python y SQL) |
| **Explorar** | Filtrar, ordenar y paginar cualquier tabla, y descargar exactamente esas filas en CSV (o CSV para Excel, con `;` y decimales con coma) |
| **Salud** | Estado de cada fuente: última carga, historial reciente, reglas incumplidas y la salud de sus datos agrupada por tipo (numéricos, texto, fechas, sí/no), con botones para **actualizar**, **reemplazar el archivo** o **eliminar** la fuente |
| **Cargar datos** | Subir un archivo (CSV, Excel, JSON o Parquet) o conectar una API, revisar la vista previa y los tipos detectados, elegir la llave, las columnas obligatorias y las que se muestran en la vista previa, describir las columnas, llenar los metadatos de datos abiertos (opcional) y publicar |

El buscador superior (atajo `Ctrl+K`) salta a cualquier dataset, columna o
fuente. Tiene tema claro y oscuro con los colores institucionales, y en el
celular las secciones pasan a una barra inferior.

**Al publicar desde la web**, la plataforma escribe la configuración en
`sources/<nombre>.yml` (versionable en git, editable a mano), guarda el archivo
en `data/landing/`, ejecuta la carga en segundo plano y publica
`estandarizado.<nombre>`. En los CSV detecta sola el separador, la codificación y
la coma decimal, y los nombres de columna se limpian (`Largo del sépalo (cm)` →
`largo_del_sepalo_cm`) guardando el original como descripción.

**Vista previa, indicadores y bitácora.** La vista previa de la ficha muestra solo las
columnas que se marcaron al cargar (si no se marcó ninguna, la llave y las obligatorias)
y permite filtrarlas; el explorador y las descargas siempre ofrecen todas. **Indicadores**
propone KPI según los tipos y nombres de las columnas y el tema del dataset (crédito,
contratación, salud, educación), cada uno con su consulta SQL; no agrupa por columnas
con datos personales. La **Bitácora** guarda notas sobre los datos, el tratamiento, las
decisiones de limpieza y los cargues; en cada cargue la plataforma anota el suyo.

**Acceso:** sin claves configuradas (uso local) todo está abierto. Con claves, la
interfaz pide una al entrar y la recuerda en el navegador; solo las de
`PLATAFORMA_ADMIN_KEYS` ven **Cargar datos** y los botones de administración, y son las
únicas que pueden escribir y editar notas en la bitácora (leerla, puede cualquiera con acceso).
Tras 10 claves incorrectas desde una misma IP, la web y la API la bloquean 15 minutos.

**Seguridad de la instalación:**

- La aplicación corre en Docker con un usuario sin privilegios (uid 1000). El contenedor
  arranca como root solo un instante, para corregir el dueño de las carpetas montadas
  (`data/`, `sources/`, `transform/`), y enseguida cede el control: ver `docker/entrypoint.sh`.
- PostgreSQL solo acepta conexiones desde el mismo equipo (`127.0.0.1` y `::1`). Para abrirlo
  a la red, edita `ports` en `docker-compose.yml` y usa una contraseña fuerte y usuarios de
  solo lectura.
- Desde la web solo se conectan APIs públicas: una dirección que apunte a la red interna
  (localhost, rangos privados, metadatos de la nube) se rechaza. Ver
  `PLATAFORMA_PERMITIR_REDES_PRIVADAS`.
- Los archivos subidos respetan `PLATAFORMA_MAX_SUBIDA_MB` y se guardan primero en un
  temporal: si la subida falla o se pasa del límite, el archivo anterior queda intacto.

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
| `GET /sources/{name}/calidad-mintic` | Evaluación de calidad según MinTIC de la última carga: reporte antes y después de la limpieza y comparativo |
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
| `metadata` | no | Metadatos de datos abiertos (DCAT): `publisher`, `contact_email`, `category`, `update_frequency`, `coverage`, `license` y `column_descriptions` |
| `preview_columns` | no | Columnas que muestra la vista previa. Vacío: la llave y las obligatorias, o todas |
| `tags`, `owner`, `schedule`, `enabled`, `max_records` | no | Metadatos y límites operativos |

Reglas de contrato disponibles: `not_null`, `unique`, `non_negative`, `range`,
`in_set` y `regex`. Cada una tiene `severity` (`warn` o `error`) y
`max_failure_rate` (tolerancia como fracción de filas).

Tipos de fuente soportados: APIs REST que devuelven JSON (cuatro tipos de
paginación y de autenticación) y archivos CSV, Excel, Parquet o JSON, locales o
por URL. La lectura directa desde otras bases de datos aún no está disponible.

`secop_procesos.yml` queda como ejemplo de fuente grande e incremental, pero
deshabilitada: SECOP tiene más de 1,5 millones de registros en 2026 y cada carga
tarda minutos. Para usarla, cambia `enabled` a `true` y habilita sus dos modelos
dbt en `transform/dbt_project.yml`.

### Agregar una fuente nueva

Lo más simple es **Cargar datos** en la web. Por terminal:

1. Copia `sources/_plantilla.yml` como `sources/<nombre>.yml` y ajústalo.
2. `plataforma validate` y `plataforma inspect <nombre>` para ver los campos reales.
3. `plataforma ingest <nombre>`: carga y publica `estandarizado.<nombre>`.

Para una versión curada (columnas renombradas, reglas de negocio), crea un modelo
dbt en `transform/models/estandarizado/` con la macro
`origen_vigente('<nombre>', ['<llave>'])`, ejecuta `plataforma dbt-sources` y
`dbt build`. Desde ese momento dbt se encarga de la tabla y la publicación
automática no la toca.

### Qué hace cada ejecución

1. Registra o actualiza la fuente en `meta.sources` (con hash del YAML).
2. Lee el cursor de `meta.state` y extrae solo lo nuevo. Si `max_records` corta
   la carga a mitad de un grupo de valores, el cursor no avanza sobre ese grupo
   y se vuelve a pedir completo en la siguiente ejecución.
3. Infiere tipos (las APIs abiertas devuelven números y fechas como texto) y,
   si aparecen columnas o cambian tipos, crea una versión en `meta.schema_versions`.
4. Evalúa el contrato (`meta.quality_results`), perfila cada columna
   (`meta.column_profiles`: nulos, distintos, mínimo, máximo, media, desviación, mediana)
   y hace el diagnóstico base de calidad MinTIC sobre los registros tal como llegaron.
5. Agrega los registros crudos a `origen.<fuente>` y avanza el cursor.
6. Publica `estandarizado.<fuente>`: tipos corregidos, nombres de columna limpios,
   sin duplicados por llave y solo con cargas aprobadas. Sin llave ni campo
   incremental, cada carga es una foto completa y se publica solo la última.
7. Repite la evaluación de calidad MinTIC sobre la tabla publicada (`meta.calidad_mintic`),
   calcula el comparativo antes/después y anota el cargue en la bitácora (`meta.bitacora`).
   Si el paso 6 o el 7 fallan, la carga ya quedó guardada y el error se registra.

Los pasos 3 a 5 van en una sola transacción. Estados posibles de una ejecución:

| Estado | Significado | ¿Llega a estandarizado? |
| --- | --- | --- |
| `success` | Todo bien | sí |
| `success_with_warnings` | Falló alguna regla `warn` | sí |
| `failed_quality` | Falló una regla `error`: los datos quedan en origen como evidencia | **no** (cuarentena) |
| `failed` | Error de extracción, columnas obligatorias ausentes o cambio de esquema prohibido | no se cargó nada |

### Calidad según los lineamientos de MinTIC

Cada carga pasa por `MinTicQualityEngine` (`src/plataforma/quality/mintic/`) dos veces: sobre
los registros tal como llegaron (**antes**) y sobre la tabla publicada (**después**). El reporte
comparativo dice cuánto cambió cada criterio y qué hallazgos resolvió la limpieza.

- **Base:** Anexo 1 de la *Guía de calidad e interoperabilidad de datos abiertos* (MinTIC, v. 8,
  2025; errores ERR001 a ERR022), los criterios ISO/IEC 25012 de esa guía y, para datos
  personales, la Ley 1581 de 2012 y la Ley 1712 de 2014.
- **Qué revisa:** título y descripción, metadatos, filas y columnas mínimas, columnas sin nombre
  o sin descripción, vacíos y rellenos («N/A», «-»), tipos y formatos, datos ficticios,
  duplicados, totales mezclados con el detalle, direcciones sin coordenadas, coordenadas fuera
  de Colombia y datos personales (cédulas, correos, teléfonos, direcciones).
- **Resultado:** `score_global` (0-100), `nivel_cumplimiento`, `criterios_evaluados` (0-10 cada
  uno) y `hallazgos_errores` (código, severidad, ubicación y recomendación de MinTIC). Se ve en
  la pestaña Calidad y en `GET /sources/{fuente}/calidad-mintic`.
- **Límites declarados:** la guía no define un puntaje de 0 a 100 ni niveles; los de la
  plataforma (Excelente ≥ 95, Avanzado ≥ 80, Básico ≥ 60) son un criterio propio. Los códigos
  `PD-…` son comprobaciones propias. ERR006, ERR010, ERR012, ERR013, ERR015, ERR021 y ERR022
  requieren revisión manual. Los datos personales generan un hallazgo de severidad error, pero
  no bloquean la carga, y el reporte nunca guarda los valores.

Para agregar una regla, escribe una función `(df, metadatos) -> list[Hallazgo]` en
`quality/mintic/reglas/` y súmala a la lista `REGLAS` de su módulo.

## Estructura del repositorio

```text
.
├── sources/                    # REGISTRO DE FUENTES: un YAML por fuente
│   ├── _plantilla.yml          # referencia completa del formato (no se carga)
│   ├── secop_procesos.yml      # ejemplo de API grande e incremental (deshabilitada)
│   └── ejemplo_archivo.yml     # ejemplo de fuente tipo archivo (deshabilitada)
├── src/plataforma/
│   ├── registry/               # modelo pydantic del YAML + cargador con ${VARIABLES}
│   ├── ingestion/              # extractores REST y archivo, motor genérico
│   ├── quality/                # inferencia de tipos, perfilado y contratos
│   │   └── mintic/             # motor de calidad MinTIC: reglas, puntaje y comparativo
│   ├── storage/                # DDL del catálogo, escritura en meta.* y origen.*
│   ├── api/                    # FastAPI genérica: catálogo + datasets, con clave de acceso
│   ├── web/                    # plataforma web: páginas, carga de datos (carga.py), cargas en
│   │                           # segundo plano (tareas.py), plantillas, estilos, HTMX y fuentes
│   ├── publicacion.py          # publicación automática de estandarizado.<fuente> (la limpieza)
│   ├── indicadores.py          # sugerencias de KPI según el esquema y el tema
│   ├── consultas.py            # lectura, filtros y CSV compartidos por API, web y MCP
│   ├── seguridad.py            # bloqueo de APIs internas (SSRF) y límite de intentos de clave
│   ├── mcp_server.py           # servidor MCP de solo lectura para asistentes de IA
│   └── cli.py                  # comando `plataforma`
├── transform/                  # proyecto dbt (estandarizado y analitico)
│   ├── macros/plataforma.sql   # origen_vigente(), a_numero(), a_fecha()
│   └── models/{estandarizado,analitico}/
├── docker/                     # entrypoint.sh: arranque del contenedor sin privilegios
├── tests/                      # unitarias + integración contra PostgreSQL
├── ejemplos/                   # datos pequeños para probar (Iris, API DIVIPOLA)
├── analisis/                   # cifras del anteproyecto: copia fechada de la evaluación de MinTIC
├── data/landing/               # archivos subidos desde la web (no se versionan)
├── iniciar.bat                 # arranque en Windows
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
sus esquemas, así que nunca apuntes esta variable a la base real. Con Docker, crea
una base aparte y bórrala al terminar:

```bash
docker compose up -d db
docker compose exec db createdb -U plataforma plataforma_test
PLATAFORMA_TEST_DATABASE_URL=postgresql+psycopg://plataforma:plataforma@localhost:5432/plataforma_test pytest -q
docker compose exec db dropdb -U plataforma plataforma_test
```

Las pruebas unitarias cubren el motor de calidad MinTIC (`tests/test_mintic.py`: un caso
por error frecuente, puntaje, nivel y comparativo), las sugerencias de indicadores
(`tests/test_indicadores.py`), la seguridad (`tests/test_seguridad.py`: APIs internas
bloqueadas y límite de intentos), la selección de columnas y los formatos de la web.

La prueba de integración simula una API y hace tres cargas incrementales, que
incluyen un cambio de esquema y una regla en cuarentena. También verifica que el
catálogo no guarde secretos, recorre todos los endpoints, comprueba la clave de
la API y los permisos del usuario de solo lectura, prueba las herramientas MCP
y recorre la plataforma web: catálogo, fichas, filtros, descargas e ingreso con clave.
También sube un archivo desde la web, lo publica, lo reemplaza y lo elimina, y
comprueba que la publicación automática excluya las cargas en cuarentena y
respete las tablas que construye dbt. Sobre ese mismo dataset verifica la vista
previa filtrada y con solo las columnas elegidas, la salud por tipo de dato, los
reportes de calidad MinTIC con su comparativo, los indicadores sugeridos y la
bitácora (agregar, editar, permisos y la nota automática de cada cargue).

## Hoja de ruta

- Asistente «Pregúntale a los datos» en la web, con Groq como modelo de pruebas.
- Reconocer números con coma decimal en las respuestas de APIs (p. ej. coordenadas de DIVIPOLA);
  hoy el motor de calidad los reporta (ERR019) pero la publicación no los convierte.
- Limpieza más completa en la publicación (recortar espacios, estandarizar rellenos como
  «N/A» y valores vacíos), para que el comparativo antes/después de MinTIC mida más mejoras.
- Detección de datos personales por contenido y no solo por patrones y nombres de columna,
  y anonimización guiada con las directrices del DANE. Hoy solo se advierte.
- Autores de la bitácora ligados a cuentas de usuario, en lugar de un nombre escrito a mano.
- Cargas automáticas con un orquestador (Dagster o Airflow) que lea `schedule` de cada YAML.
- Límites de uso por clave en la API.
- Detección de derivas sobre `meta.column_profiles`: PSI y pruebas de
  Kolmogorov-Smirnov entre cargas, gráficos de control para tasas de nulos.
- Conector para leer otras bases de datos, con anonimización de datos personales.
- Migración del almacenamiento a Parquet/Iceberg sin tocar el registro, la ingesta ni la API.

## Licencia

Pendiente de definir con la Universidad Santo Tomás. Hasta entonces, el código
no tiene una licencia de uso abierta.
