"""Frontend web de la plataforma (plantillas Jinja + HTMX, servidas por la app FastAPI)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .bitacora import router as router_bitacora
from .carga import SinPermiso
from .carga import router as router_carga
from .rutas import RequiereIngreso, render, router


def instalar_frontend(app: FastAPI) -> None:
    """Monta los archivos estáticos, las páginas y la redirección al formulario de ingreso."""
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(router)
    app.include_router(router_carga)
    app.include_router(router_bitacora)

    @app.exception_handler(SinPermiso)
    async def _sin_permiso(request: Request, exc: SinPermiso) -> Response:
        return render(request, "error.html", 403, titulo="Necesitas una clave de administración",
                      mensaje="Cargar, actualizar o eliminar datos requiere una clave de PLATAFORMA_ADMIN_KEYS. "
                              "Cierra sesión e ingresa con esa clave.", seccion=None, con_sesion=True)

    @app.exception_handler(RequiereIngreso)
    async def _a_ingresar(request: Request, exc: RequiereIngreso) -> Response:
        url = f"/ingresar?{urlencode({'siguiente': exc.destino})}"
        if request.headers.get("HX-Request") == "true":   # HTMX no sigue redirecciones de página
            return Response(status_code=401, headers={"HX-Redirect": url})
        return RedirectResponse(url, 303)
