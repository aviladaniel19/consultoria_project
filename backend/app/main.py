"""
main.py — Punto de entrada de la API VIGÍA.

FastAPI con estructura modular de routers por dominio.

Ejecución local:
    uvicorn app.main:app --reload --port 8000

Con Docker:
    docker-compose up
"""

import functools
import logging
import sys
import time

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi import Request

from app.config import get_settings
from app.routers import (
    auth_router,
    proyectos_router,
    indicadores_router,
    afirmaciones_router,
    datasets_router,
)

# ──────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────

# En Windows, si stdout/stderr están redirigidos (logs, servicios), Python usa
# cp1252 y cualquier print() con emojis lanza UnicodeEncodeError → HTTP 500.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
)
logger = logging.getLogger("vigia.api")


# ──────────────────────────────────────────────
# DECORADOR: log_request
# ──────────────────────────────────────────────

def log_request(func):
    """
    Decorador de comportamiento: registra entrada y tiempo de ejecución de cada endpoint.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        inicio = time.perf_counter()
        logger.info(f"-> {func.__name__}() llamado")
        try:
            resultado = await func(*args, **kwargs)
            ms = (time.perf_counter() - inicio) * 1000
            logger.info(f"[OK] {func.__name__}() en {ms:.1f}ms")
            return resultado
        except HTTPException:
            raise
        except Exception as exc:
            ms = (time.perf_counter() - inicio) * 1000
            logger.error(f"[ERR] {func.__name__}() fallo en {ms:.1f}ms -> {exc}")
            raise
    return wrapper


# ──────────────────────────────────────────────
# INSTANCIA FASTAPI
# ──────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="VIGÍA API",
    description=(
        "Backend de la Red de Monitoreo Vigía — Facultad de Estadística USTA.\n\n"
        "Monitoreo estadístico de proyectos con agentes de IA para contraste de afirmaciones, "
        "cálculo de índices compuestos y análisis de datasets."
    ),
    version="1.0.0",
    contact={
        "name": "Vigía — USTA Estadística",
        "email": "estadistica@usta.edu.co",
    },
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "Core",          "description": "Health check y UI"},
        {"name": "Auth",          "description": "Autenticación JWT"},
        {"name": "Proyectos",     "description": "CRUD y 4 índices Vigía"},
        {"name": "Indicadores",   "description": "Métricas por proyecto"},
        {"name": "Afirmaciones",  "description": "Contraste de afirmaciones de impacto"},
        {"name": "Datasets",      "description": "Carga y análisis estadístico"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# ──────────────────────────────────────────────
# STARTUP: inicializar tablas
# ──────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    from app.database import engine, Base
    from app.models.db_models import (  # noqa: F401
        Proyecto, Indicador, Afirmacion, Dataset, AlertaLog,
    )
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Base de datos inicializada (tablas verificadas)")


# ──────────────────────────────────────────────
# MANEJADOR DE ERRORES 422
# ──────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errores = []
    for error in exc.errors():
        campo = " → ".join(str(loc) for loc in error["loc"])
        errores.append({
            "campo": campo,
            "mensaje": error.get("msg"),
            "tipo_error": error.get("type"),
            "valor_recibido": error.get("input"),
        })
    logger.warning(
        f"[422] {request.method} {request.url.path} → {len(errores)} error(es)"
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "estado": "error_validacion",
            "codigo": 422,
            "mensaje": "Los datos enviados contienen errores. Revise cada campo.",
            "errores": errores,
        },
    )


# ──────────────────────────────────────────────
# ROUTERS
# ──────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(proyectos_router)
app.include_router(indicadores_router)
app.include_router(afirmaciones_router)
app.include_router(datasets_router)


# ──────────────────────────────────────────────
# ENDPOINTS CORE
# ──────────────────────────────────────────────

@app.get("/", tags=["Core"], summary="Dashboard Frontend UI", include_in_schema=False)
async def serve_ui():
    """Sirve el dashboard Vigía (index.html)."""
    import os
    file_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"mensaje": "Dashboard aún no disponible. API activa en /docs"}


@app.get("/health", tags=["Core"], summary="Health check de la API")
@log_request
async def health_check():
    """Verifica que la API está operativa."""
    return {
        "status": "ok",
        "app": "VIGÍA API",
        "version": "1.0.0",
        "docs": "/docs",
    }
