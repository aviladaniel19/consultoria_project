# VIGÍA API

Backend de la **Red de Monitoreo Vigía** — Facultad de Estadística, USTA.

API REST construida con FastAPI que permite el monitoreo estadístico de proyectos de impacto social mediante agentes de IA para el contraste de afirmaciones, cálculo de índices compuestos (Avance, Capacidad, Veracidad, Impacto) y análisis de datasets.

---

## Tabla de contenidos

- [Resumen](#resumen)
- [Stack tecnológico](#stack-tecnológico)
- [Arquitectura](#arquitectura)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Modelo de datos](#modelo-de-datos)
- [Endpoints de la API](#endpoints-de-la-api)
- [Instalación y ejecución en Windows](#instalación-y-ejecución-en-windows)
- [Despliegue con Docker](#despliegue-con-docker)
- [Variables de entorno](#variables-de-entorno)

---

## Resumen

- **Gestión de proyectos**: CRUD completo de proyectos de impacto social con estados (ACTIVO, PAUSADO, CERRADO).
- **Indicadores de desempeño**: Registro y seguimiento de métricas con cálculo automático de porcentaje de avance.
- **4 Índices Vigía**: Cálculo automático de Índice de Avance, Capacidad, Veracidad e Impacto por proyecto.
- **Agente 01 — Contraste de afirmaciones**: Análisis individual o batch de afirmaciones de impacto con IA (Gemini → Groq → modo offline). Genera veredictos: `SUSTENTADA`, `REFUTADA` o `SIN DATOS`.
- **Sistema de alertas automáticas**: Generación de `AlertaLog` cuando una afirmación es refutada (severidad `ALTA`) o tiene confianza baja (severidad `MEDIA`).
- **Carga y análisis de datasets**: Subida de archivos CSV/Excel con análisis estadístico automatizado de tipos de variables, datos faltantes y patrones de missingness.
- **Autenticación JWT**: Login con OAuth2PasswordBearer, tokens HS256, expiración configurable.
- **Dashboard frontend integrado**: Sirve `static/index.html` directamente desde la API en `/`.
- **Documentación interactiva**: Disponible en `/docs` (Swagger UI) y `/redoc`.

---

## Stack tecnológico

| Capa               | Tecnología              | Versión        |
|--------------------|-------------------------|----------------|
| Framework API      | FastAPI                 | >= 0.111.0     |
| Servidor ASGI      | Uvicorn                 | >= 0.29.0      |
| Validación         | Pydantic v2             | >= 2.7.0       |
| Configuración      | pydantic-settings       | >= 2.2.1       |
| ORM                | SQLAlchemy              | >= 2.0.30      |
| Migraciones        | Alembic                 | >= 1.12.0      |
| BD desarrollo      | SQLite                  | Embebida       |
| BD producción      | PostgreSQL              | 16             |
| Driver PostgreSQL  | psycopg2-binary         | >= 2.9.0       |
| Auth JWT           | python-jose             | >= 3.3.0       |
| Hashing            | passlib[bcrypt]         | >= 1.7.4       |
| Agente LLM         | LangChain + Gemini      | >= 0.3.0 / >= 0.8.0 |
| Agente LLM (alt.)  | LangChain + Groq        | >= 0.1.0       |
| Análisis datos     | pandas / numpy / scipy  | >= 2.2.0 / >= 1.26.0 / >= 1.13.0 |
| ML                 | scikit-learn            | >= 1.4.0       |
| Modelos GARCH      | statsmodels             | >= 0.14.2      |
| Exportación        | fpdf2 / openpyxl        | >= 2.7.0 / >= 3.1.0 |
| Tareas background  | APScheduler             | >= 3.10.0      |
| Contenedor         | Docker + docker-compose | 3.9            |
| Lenguaje           | Python                  | 3.11           |

---

## Arquitectura

```
Cliente (Browser / API Consumer)
        |
        | HTTP/HTTPS
        v
+-------------------------------------------+
|           FastAPI Application             |
|                                           |
|  Middlewares:                             |
|    - CORSMiddleware (allow_origins=*)     |
|    - RequestValidationError Handler       |
|    - log_request() decorator             |
|                                           |
|  Routers (módulos por dominio):           |
|    /auth        -> auth.py                |
|    /proyectos   -> proyectos.py           |
|    /proyectos/{id}/indicadores            |
|                 -> indicadores.py         |
|    /proyectos/{id}/afirmaciones           |
|                 -> afirmaciones.py        |
|    /datasets    -> datasets.py            |
|                                           |
|  Servicios:                               |
|    agente_01.py -> LLM (Gemini / Groq)   |
|    risk_service.py -> calculos estadisticos|
|    ml_service.py -> modelos ML            |
|                                           |
|  ORM (SQLAlchemy):                        |
|    db_models.py -> Proyecto, Indicador,   |
|                   Afirmacion, Dataset,    |
|                   AlertaLog               |
+-------------------------------------------+
        |                    |
        | SQLAlchemy          | LLM APIs (HTTP)
        v                    v
  SQLite (dev)      Gemini API / Groq API
  PostgreSQL (prod)
```

**Flujo del Agente 01 (contraste de afirmaciones):**

```
POST /proyectos/{id}/afirmaciones/{aff_id}/contrastar
        |
        v
  agente_01.contrastar_afirmacion(texto)
        |
        |-- 1. Intenta con Gemini (GOOGLE_API_KEY)
        |-- 2. Fallback a Groq   (GROQ_API_KEY)
        |-- 3. Fallback offline  (respuesta estatica)
        |
        v
  Veredicto: SUSTENTADA | REFUTADA | SIN DATOS
        |
        |-- Persiste en DB (afirmacion.veredicto, confianza)
        |-- Si REFUTADA -> AlertaLog (severidad ALTA)
        |-- Si confianza < 0.4 -> AlertaLog (severidad MEDIA)
        v
  ContrasteResponse JSON
```

---

## Estructura del proyecto

```
vigia/
+-- backend/                    # Código fuente de la API
|   +-- app/
|   |   +-- main.py             # Entrypoint: instancia FastAPI, routers, middlewares
|   |   +-- config.py           # BaseSettings (pydantic-settings), variables de entorno
|   |   +-- database.py         # Engine SQLAlchemy, SessionLocal, get_db()
|   |   +-- dependencies.py     # Dependencias compartidas de FastAPI
|   |   +-- models.py           # Schemas Pydantic request/response (módulo financiero)
|   |   +-- services.py         # Servicios monolíticos (módulo financiero legacy)
|   |   +-- models/
|   |   |   +-- db_models.py    # Modelos ORM: Proyecto, Indicador, Afirmacion, Dataset, AlertaLog
|   |   |   +-- schemas.py      # Schemas Pydantic del módulo Vigía (CRUD)
|   |   +-- routers/
|   |   |   +-- __init__.py     # Exporta todos los routers
|   |   |   +-- auth.py         # POST /auth/login, GET /auth/me
|   |   |   +-- proyectos.py    # CRUD /proyectos + índices Vigía
|   |   |   +-- indicadores.py  # CRUD /proyectos/{id}/indicadores
|   |   |   +-- afirmaciones.py # CRUD + Agente 01 /proyectos/{id}/afirmaciones
|   |   |   +-- datasets.py     # Upload + análisis /datasets
|   |   +-- services/
|   |   |   +-- agente_01.py    # Agente IA: contraste (Gemini/Groq/offline)
|   |   |   +-- risk_service.py # Cálculos estadísticos de riesgo financiero
|   |   |   +-- ml_service.py   # Modelos de ML (predicción)
|   |   |   +-- capm.py         # Modelo CAPM
|   |   |   +-- garch_models.py # Modelos GARCH(1,1) y variantes
|   |   |   +-- markowitz.py    # Frontera eficiente de Markowitz
|   |   |   +-- var_cvar.py     # VaR (paramétrico, histórico, Montecarlo) y CVaR
|   |   |   +-- signals.py      # Señales de trading técnicas
|   |   |   +-- indicators.py   # Indicadores técnicos (RSI, MACD, Bollinger, etc.)
|   |   |   +-- returns.py      # Cálculo de rendimientos y estadísticas
|   |   |   +-- macro_benchmark.py # Indicadores macroeconómicos (FRED API)
|   |   |   +-- data_loader.py  # Carga de precios vía Yahoo Finance
|   |   |   +-- api_client.py   # Cliente HTTP para APIs externas
|   |   |   +-- fixed_income.py # Renta fija
|   |   |   +-- derivatives.py  # Derivados financieros
|   |   +-- static/
|   |       +-- index.html      # Dashboard frontend (servido en /)
|   +-- data/
|   |   +-- uploads/            # Archivos CSV/Excel subidos por /datasets/upload
|   +-- limpieza_datos/
|   |   +-- analizador.py       # AnalizadorDatos: tipos de variables, datos faltantes
|   +-- Dockerfile              # Imagen Docker del backend (python:3.11-slim)
|   +-- requirements.txt        # Dependencias Python del backend
|   +-- seed.py                 # Script para poblar la BD con datos de prueba
|   +-- train_model.py          # Script de entrenamiento de modelos ML
|   +-- vigia_dev.db            # Base de datos SQLite (desarrollo local)
|   +-- .env.example            # Plantilla de variables de entorno
+-- src/                        # Módulos del módulo financiero legacy (standalone)
+-- data/                       # Datasets de referencia del proyecto
+-- docker-compose.yml          # Stack completo: PostgreSQL + pgAdmin + Backend
+-- iniciar_dashboard.bat       # Script de inicio rápido en Windows
+-- requirements.txt            # Dependencias raíz (referencia)
+-- README.md                   # Este archivo
```

---

## Modelo de datos

```
proyectos
+---------------------+--------------+----------------------------+
| Campo               | Tipo         | Notas                      |
+---------------------+--------------+----------------------------+
| id (PK)             | String(36)   | UUID                       |
| nombre              | String(120)  | NOT NULL                   |
| descripcion         | Text         |                            |
| responsable         | String(100)  |                            |
| fecha_inicio        | Date         | NULL                       |
| estado              | String(20)   | ACTIVO/PAUSADO/CERRADO     |
| created_at          | DateTime     | UTC                        |
+---------------------+--------------+----------------------------+

indicadores
+---------------------+--------------+----------------------------+
| Campo               | Tipo         | Notas                      |
+---------------------+--------------+----------------------------+
| id (PK)             | String(36)   | UUID                       |
| proyecto_id (FK)    | String(36)   | -> proyectos.id            |
| nombre              | String(100)  | NOT NULL                   |
| formula             | String(200)  |                            |
| valor_meta          | Float        | NULL                       |
| valor_real          | Float        | NULL                       |
| fecha_medicion      | DateTime     |                            |
| created_at          | DateTime     |                            |
+---------------------+--------------+----------------------------+

afirmaciones
+---------------------+--------------+----------------------------+
| Campo               | Tipo         | Notas                      |
+---------------------+--------------+----------------------------+
| id (PK)             | String(36)   | UUID                       |
| proyecto_id (FK)    | String(36)   | -> proyectos.id            |
| texto               | Text         | NOT NULL                   |
| veredicto           | String(50)   | SUSTENTADA/REFUTADA/SIN DATOS |
| fuente_url          | String(500)  | NULL                       |
| confianza           | Float        | 0.0 - 1.0                  |
| agente_id           | String(50)   | ej: agente-01-gemini       |
| created_at          | DateTime     |                            |
+---------------------+--------------+----------------------------+

datasets
+---------------------+--------------+----------------------------+
| Campo               | Tipo         | Notas                      |
+---------------------+--------------+----------------------------+
| id (PK)             | String(36)   | UUID                       |
| proyecto_id (FK)    | String(36)   | -> proyectos.id (NULL OK)  |
| nombre              | String(120)  | NOT NULL                   |
| descripcion         | Text         |                            |
| s3_path             | String(500)  | Ruta local del archivo     |
| created_at          | DateTime     |                            |
+---------------------+--------------+----------------------------+

alertas_log
+---------------------+--------------+----------------------------+
| Campo               | Tipo         | Notas                      |
+---------------------+--------------+----------------------------+
| id (PK)             | Integer      | Autoincrement              |
| timestamp           | DateTime     | Indexado                   |
| proyecto_id (FK)    | String(36)   | -> proyectos.id            |
| tipo_alerta         | String(50)   | AFIRMACION_REFUTADA/VERACIDAD_BAJA |
| mensaje             | Text         | NOT NULL                   |
| severidad           | String(20)   | ALTA / MEDIA / BAJA        |
+---------------------+--------------+----------------------------+

Relaciones:
  proyectos 1--N indicadores   (cascade delete)
  proyectos 1--N afirmaciones  (cascade delete)
  proyectos 1--N datasets      (cascade delete)
  proyectos 1--N alertas_log
```

---

## Endpoints de la API

> Documentación interactiva disponible en:
> - **Swagger UI**: `http://localhost:8000/docs`
> - **ReDoc**: `http://localhost:8000/redoc`

### Core

| Método | Ruta      | Descripción                              | Auth |
|--------|-----------|------------------------------------------|------|
| GET    | `/`       | Sirve el dashboard frontend (index.html) | No   |
| GET    | `/health` | Health check: estado y versión de la API | No   |

### Auth

| Método | Ruta          | Descripción                                 | Auth |
|--------|---------------|---------------------------------------------|------|
| POST   | `/auth/login` | Genera token JWT (form: username/password)  | No   |
| GET    | `/auth/me`    | Perfil del usuario autenticado              | Sí   |

**Credenciales de demo:**
- `admin` / `vigia2025` (rol: admin)
- `monitor` / `vigia2025` (rol: lector)

### Proyectos

| Método | Ruta                      | Descripción                                       | Auth |
|--------|---------------------------|---------------------------------------------------|------|
| GET    | `/proyectos/`             | Listar proyectos (paginación + filtro por estado) | No   |
| POST   | `/proyectos/`             | Crear nuevo proyecto                              | Sí   |
| GET    | `/proyectos/{id}`         | Obtener proyecto por ID                           | No   |
| PUT    | `/proyectos/{id}`         | Actualizar proyecto                               | Sí   |
| DELETE | `/proyectos/{id}`         | Eliminar proyecto                                 | Sí   |
| GET    | `/proyectos/{id}/indices` | Calcular los 4 índices Vigía del proyecto         | No   |
| GET    | `/proyectos/{id}/alertas` | Listar alertas del proyecto (últimas 50)          | No   |

### Indicadores

| Método | Ruta                                   | Descripción                       | Auth |
|--------|----------------------------------------|-----------------------------------|------|
| GET    | `/proyectos/{id}/indicadores/`         | Listar indicadores del proyecto   | No   |
| POST   | `/proyectos/{id}/indicadores/`         | Crear indicador para el proyecto  | Sí   |
| PUT    | `/proyectos/{id}/indicadores/{ind_id}` | Actualizar valores del indicador  | Sí   |
| DELETE | `/proyectos/{id}/indicadores/{ind_id}` | Eliminar indicador                | Sí   |

### Afirmaciones

| Método | Ruta                                                      | Descripción                                     | Auth |
|--------|-----------------------------------------------------------|-------------------------------------------------|------|
| GET    | `/proyectos/{id}/afirmaciones/`                          | Listar afirmaciones del proyecto                | No   |
| POST   | `/proyectos/{id}/afirmaciones/`                          | Registrar afirmación para contrastar            | Sí   |
| DELETE | `/proyectos/{id}/afirmaciones/{aff_id}`                  | Eliminar afirmación                             | Sí   |
| POST   | `/proyectos/{id}/afirmaciones/{aff_id}/contrastar`       | Agente 01: contrastar afirmación individual     | Sí   |
| POST   | `/proyectos/{id}/afirmaciones/contrastar-todas`          | Agente 01: contrastar todas las pendientes      | Sí   |

### Datasets

| Método | Ruta                          | Descripción                                       | Auth |
|--------|-------------------------------|---------------------------------------------------|------|
| GET    | `/datasets/`                  | Listar datasets (filtro opcional por proyecto)    | No   |
| POST   | `/datasets/upload`            | Subir archivo CSV o Excel (multipart/form-data)   | Sí   |
| GET    | `/datasets/{nombre}/info`     | Resumen rápido: filas, columnas, muestra          | No   |
| POST   | `/datasets/{nombre}/analizar` | Análisis estadístico completo (tipos, faltantes)  | No   |
| DELETE | `/datasets/{nombre}`          | Eliminar dataset (disco + BD)                     | Sí   |

---

## Instalación y ejecución en Windows

### Requisitos previos

- Python 3.11 ([python.org](https://www.python.org/downloads/))
- Git ([git-scm.com](https://git-scm.com/))

### 1. Clonar el repositorio

```powershell
git clone https://github.com/tu-org/vigia.git
cd vigia
```

### 2. Crear entorno virtual e instalar dependencias

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```powershell
copy .env.example .env
```

Edita `.env` con tus claves reales (ver sección [Variables de entorno](#variables-de-entorno)).

### 4. Poblar la base de datos (opcional)

```powershell
python seed.py
```

### 5. Iniciar el servidor de desarrollo

```powershell
uvicorn app.main:app --reload --port 8000
```

La API estará disponible en `http://localhost:8000`.
La documentación Swagger en `http://localhost:8000/docs`.

### Script de inicio rápido

Desde la raíz del proyecto existe `iniciar_dashboard.bat` que activa el entorno virtual y lanza el servidor automáticamente:

```powershell
# Desde la raíz del proyecto vigia/
.\iniciar_dashboard.bat
```

El script activa `venv\Scripts\activate`, levanta Uvicorn con 4 workers en el puerto 8000 y abre el navegador en `http://localhost:8000`.

---

## Despliegue con Docker

### Stack completo (API + PostgreSQL + pgAdmin)

```powershell
# Construir e iniciar todos los servicios
docker-compose up --build

# Ejecutar en segundo plano
docker-compose up -d --build
```

Servicios disponibles:

| Servicio   | URL                          | Descripción               |
|------------|------------------------------|---------------------------|
| API        | `http://localhost:8000`      | FastAPI + Frontend        |
| Docs       | `http://localhost:8000/docs` | Swagger UI                |
| pgAdmin    | `http://localhost:5050`      | Panel de administración BD |
| PostgreSQL | `localhost:5432`             | BD: vigia / vigia_user    |

**Credenciales pgAdmin:** `admin@vigia.co` / `admin`

### Modo standalone (solo la API, BD externa)

```powershell
# Construir imagen
docker build -t vigia-backend ./backend

# Ejecutar apuntando a una BD PostgreSQL externa
docker run -d `
  --name vigia_backend `
  -p 8000:8000 `
  -e DATABASE_URL="postgresql://usuario:password@host:5432/vigia" `
  -e SECRET_KEY="tu_clave_secreta_segura" `
  -e GOOGLE_API_KEY="tu_clave_gemini" `
  -e GROQ_API_KEY="tu_clave_groq" `
  vigia-backend
```

### Detener y limpiar

```powershell
# Detener servicios
docker-compose down

# Detener y eliminar volúmenes (borra los datos de la BD)
docker-compose down -v

# Eliminar imágenes construidas
docker-compose down --rmi all
```

---

## Variables de entorno

Crea el archivo `backend/.env` copiando `backend/.env.example`. Las variables son leídas por `pydantic-settings` con prioridad: variable de entorno del sistema > `.env` > valor por defecto.

| Variable                      | Requerida | Default                                                | Descripción                                                  |
|-------------------------------|-----------|--------------------------------------------------------|--------------------------------------------------------------|
| `GOOGLE_API_KEY`              | Sí*       | `""`                                                   | API Key de Google Gemini (Agente 01, proveedor principal)    |
| `GROQ_API_KEY`                | Sí*       | `""`                                                   | API Key de Groq (Agente 01, fallback)                        |
| `SECRET_KEY`                  | **Sí**    | `clave_secreta_vigia_desarrollo_cambiar_en_produccion` | Clave para firmar tokens JWT. **Cambiar en producción.**     |
| `ALGORITHM`                   | No        | `HS256`                                                | Algoritmo de firma JWT                                       |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No        | `60`                                                   | Duración del token JWT en minutos                            |
| `DATABASE_URL`                | No        | `sqlite:///./vigia_dev.db`                             | URL de conexión a la BD. En Docker: `postgresql://vigia_user:vigia_pass@db:5432/vigia` |
| `BACKEND_HOST`                | No        | `0.0.0.0`                                              | Host de escucha del servidor                                 |
| `BACKEND_PORT`                | No        | `8000`                                                 | Puerto de escucha del servidor                               |
| `CORS_ORIGINS`                | No        | `["*"]`                                                | Orígenes permitidos en CORS. Restringir en producción.       |
| `FRED_API_KEY`                | Sí*       | —                                                      | API Key de FRED (Federal Reserve) para indicadores macro     |
| `ALPHA_VANTAGE_KEY`           | No        | `""`                                                   | API Key de Alpha Vantage (precios alternativos)              |
| `FINNHUB_KEY`                 | No        | `""`                                                   | API Key de Finnhub (datos financieros)                       |
| `VAR_CONFIDENCE_DEFAULT`      | No        | `0.95`                                                 | Nivel de confianza por defecto para VaR                      |
| `MONTECARLO_N_SIM`            | No        | `10000`                                                | Número de simulaciones Montecarlo                            |
| `GARCH_WINDOW`                | No        | `252`                                                  | Ventana temporal para modelos GARCH (días bursátiles)        |
| `BENCHMARK_TICKER`            | No        | `^GSPC`                                                | Ticker del índice de referencia (S&P 500)                    |
| `FRED_RF_SERIE`               | No        | `DGS3MO`                                               | Serie FRED para la tasa libre de riesgo (Treasury 3 meses)   |

> **\*Sí\*** = Requerida para las funcionalidades de agentes IA y análisis financiero. Sin ellas, el Agente 01 opera en modo `offline`.

**Generar una `SECRET_KEY` segura:**

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
