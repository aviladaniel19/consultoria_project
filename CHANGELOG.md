# Changelog — VIGÍA API

Todos los cambios notables de este proyecto se documentan en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/) y el proyecto sigue [Semantic Versioning](https://semver.org/).

---

## [1.0.0] — 2026-10-01

Versión inicial de producción de la API VIGÍA — Red de Monitoreo Estadístico, Facultad de Estadística USTA.

### Added

#### Backend FastAPI

- **Módulo Auth** (`/auth`): autenticación JWT con OAuth2PasswordBearer, hashing bcrypt, usuarios demo `admin` y `monitor`, expiración configurable por variable de entorno.
- **Módulo Proyectos** (`/proyectos`): CRUD completo de proyectos de impacto social con estados `ACTIVO`, `PAUSADO`, `CERRADO` y paginación.
- **Módulo Indicadores** (`/proyectos/{id}/indicadores`): CRUD de indicadores de desempeño con cálculo automático de porcentaje de avance (`valor_real / valor_meta * 100`).
- **4 Índices Vigía** (`/proyectos/{id}/indices`):
  - Índice de Avance: promedio de avance de todos los indicadores.
  - Índice de Capacidad: fracción de indicadores con valor real registrado.
  - Índice de Veracidad: afirmaciones SUSTENTADAS / total contrastadas.
  - Índice de Impacto: pendiente de implementación (Agente 02).
- **Módulo Afirmaciones** (`/proyectos/{id}/afirmaciones`): registro, listado y eliminación de afirmaciones de impacto.
- **Agente 01 — Contraste de afirmaciones**: análisis individual y batch de afirmaciones usando LLM con patrón fallback Gemini → Groq → modo offline. Veredictos: `SUSTENTADA`, `REFUTADA`, `SIN DATOS`.
- **Sistema de alertas automáticas**: generación de `AlertaLog` al detectar afirmación refutada (severidad `ALTA`) o confianza < 0.4 (severidad `MEDIA`).
- **Módulo Datasets** (`/datasets`): subida de archivos CSV/Excel, análisis estadístico automatizado con `AnalizadorDatos` (tipos de variables, datos faltantes, patrones de missingness, recomendaciones).
- **Dashboard frontend integrado**: `GET /` sirve `static/index.html` directamente desde la API.
- **Health check**: `GET /health` retorna estado, nombre y versión de la API.

#### Infraestructura

- **Base de datos**: SQLAlchemy ORM con SQLite (desarrollo) y PostgreSQL 16 (producción) sin cambios en el código ORM.
- **Modelos ORM**: `Proyecto`, `Indicador`, `Afirmacion`, `Dataset`, `AlertaLog` con relaciones 1:N y cascade delete.
- **Schemas Pydantic v2**: validación completa de entrada/salida en todos los endpoints.
- **Configuración centralizada**: `BaseSettings` (pydantic-settings) con soporte de múltiples archivos `.env`.
- **CORS**: middleware configurado, orígenes restringibles por variable de entorno.
- **Middleware de logging**: decorador `@log_request` que registra tiempos de respuesta por endpoint.
- **Manejador 422**: respuestas de error de validación estructuradas con detalle por campo.

#### Docker

- `Dockerfile` con imagen `python:3.11-slim`, optimizado con cache de capas (dependencias antes que código).
- `docker-compose.yml`: stack completo con PostgreSQL 16, pgAdmin 4 y backend FastAPI.
- Health checks configurados en todos los servicios.

#### Documentación

- `README.md`: técnico y completo con arquitectura ASCII, modelo de datos, tabla de 24 endpoints, guía de instalación Windows y despliegue Docker.
- `CONTRIBUTING.md`: flujo de contribución adaptado a la arquitectura Vigía.
- `CHANGELOG.md`: este archivo.
- `.env.example`: plantilla con todas las variables de entorno documentadas.
- `iniciar_dashboard.bat`: script de inicio rápido para Windows.

### Technical Notes

- Agente 01 procesa afirmaciones en batch secuencialmente con `asyncio.sleep(0.5)` entre llamadas para respetar rate limits de las APIs LLM.
- La sesión de BD se inyecta por request con `Depends(get_db)` y se cierra en el bloque `finally`.
- `get_settings()` usa `@lru_cache` para instanciar `Settings` una única vez por ciclo de vida.

---

## [Próximas versiones]

- `[1.1.0]` — Agente 02: cálculo del Índice de Impacto con análisis de beneficiarios.
- `[1.2.0]` — Agente 03: detección de anomalías estadísticas en series de indicadores.
- `[1.3.0]` — Agente 04: pipeline completo de análisis estadístico y ML sobre datasets subidos.
- `[2.0.0]` — Integración con base de datos de usuarios real (tabla `User` + roles), reemplazo de usuarios demo.

Envía tus feature requests en [Issues](../../issues).
