"""
__init__.py — Registro centralizado de routers de Vigía.
"""
from app.routers.auth import router as auth_router
from app.routers.proyectos import router as proyectos_router
from app.routers.indicadores import router as indicadores_router
from app.routers.afirmaciones import router as afirmaciones_router
from app.routers.datasets import router as datasets_router

__all__ = [
    "auth_router",
    "proyectos_router",
    "indicadores_router",
    "afirmaciones_router",
    "datasets_router",
]
