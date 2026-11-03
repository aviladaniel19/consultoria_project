"""Frontend web: catálogo, ficha de cada dataset, explorador con filtros y salud de las fuentes.

Plantillas Jinja + HTMX servidas por la misma app FastAPI: un solo proceso, sin paso de
compilación. Las peticiones de HTMX (cabecera HX-Request) reciben solo el fragmento que cambia.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import Connection

from .. import consultas
from ..config import get_settings, split_csv
from ..storage.db import get_engine
from . import datos

AQUI = Path(__file__).parent
COOKIE = "pd_clave"
COLOMBIA = timezone(timedelta(hours=-5), "COT")   # Colombia no tiene horario de verano
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
TAMANOS_PAGINA = (25, 50, 100, 250)
ESTADOS = {   # estado de una carga -> (clase css, ícono, etiqueta)
    "success": ("ok", "✓", "Carga exitosa"),
    "success_with_warnings": ("aviso", "▲", "Con advertencias"),
    "failed_quality": ("cuarentena", "■", "En cuarentena"),
    "failed": ("error", "✕", "Falló"),
    "running": ("neutro", "…", "En curso"),
    None: ("neutro", "○", "Sin cargas"),
}
REGLAS = {"not_null": "sin vacíos", "unique": "valores únicos", "non_negative": "no negativo",
          "range": "dentro de rango", "in_set": "valores permitidos", "regex": "formato"}

templates = Jinja2Templates(directory=AQUI / "templates")
router = APIRouter(include_in_schema=False)


# ------------------------------------------------------------------------ formatos
def fmt_num(v: Any, decimales: int = 0) -> str:
    """Formato de Colombia: punto de miles y coma decimal."""
    if v is None:
        return "—"
    texto = f"{float(v):,.{decimales}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_compacto(v: Any) -> str:
    """1.250.000.000 -> '1.250 M' (millones), útil para precios en pesos."""
    if v is None:
        return "—"
    v = float(v)
    for umbral, sufijo in ((1e12, " billones"), (1e6, " M"), (1e3, " mil")):
        if abs(v) >= umbral:
            return fmt_num(v / umbral, 1 if abs(v) < 100 * umbral else 0) + sufijo
    return fmt_num(v, 2 if v % 1 else 0)


def _local(v: datetime) -> datetime:
    return (v if v.tzinfo else v.replace(tzinfo=UTC)).astimezone(COLOMBIA)


def fmt_fecha(v: Any, hora: bool = True) -> str:
    if v is None:
        return "—"
    if isinstance(v, datetime):
        v = _local(v)
        base = f"{v.day:02d} {MESES[v.month - 1]} {v.year}"
        return f"{base}, {v:%H:%M}" if hora else base
    return f"{v.day:02d} {MESES[v.month - 1]} {v.year}"


def fmt_hace(v: datetime | None) -> str:
    if v is None:
        return "nunca"
    s = (datetime.now(UTC) - _local(v)).total_seconds()
    if s < 90:
        return "hace un momento"
    for unidad, segundos, plural in (("día", 86400, "días"), ("hora", 3600, "horas"), ("minuto", 60, "minutos")):
        if s >= segundos:
            n = int(s // segundos)
            return f"hace {n} {unidad if n == 1 else plural}"
    return "hace un momento"


def fmt_pct(v: Any, decimales: int = 1) -> str:
    return "—" if v is None else fmt_num(float(v) * 100, decimales) + " %"


def fmt_celda(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return fmt_fecha(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return fmt_num(v, 0 if float(v).is_integer() else 2)
    if type(v).__name__ == "Decimal":
        return fmt_num(v, 0 if v == v.to_integral_value() else 2)
    if hasattr(v, "isoformat"):
        return fmt_fecha(v, hora=False)
    return str(v)


templates.env.filters.update(num=fmt_num, compacto=fmt_compacto, fecha=fmt_fecha, hace=fmt_hace,
                             pct=fmt_pct, celda=fmt_celda)
templates.env.globals.update(ESTADOS=ESTADOS, REGLAS=REGLAS, OPERADORES=consultas.OPERADORES,
                             NUMERICOS=datos.NUMERICOS)


# -------------------------------------------------------------------------- acceso
class RequiereIngreso(Exception):
    def __init__(self, destino: str):
        self.destino = destino


def _clave_valida(clave: str | None) -> bool:
    claves = split_csv(get_settings().api_keys)
    return bool(clave) and any(secrets.compare_digest(clave, k) for k in claves)


def sesion(request: Request) -> bool:
    """Si la API tiene claves, el frontend pide una de ellas una vez y la guarda en una cookie.
    Devuelve True cuando hay sesión que se pueda cerrar."""
    if not split_csv(get_settings().api_keys):
        return False
    if _clave_valida(request.cookies.get(COOKIE)):
        return True
    destino = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    raise RequiereIngreso(destino)


def _destino_seguro(destino: str | None) -> str:
    # solo rutas locales: evita que el enlace de ingreso redirija a otro sitio
    return destino if destino and destino.startswith("/") and not destino.startswith("//") else "/"


def conexion():
    with get_engine().connect() as conn:
        yield conn


def render(request: Request, plantilla: str, status_code: int = 200, **contexto: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, plantilla, contexto, status_code=status_code)


def es_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def no_encontrado(request: Request, mensaje: str, con_sesion: bool) -> HTMLResponse:
    return render(request, "error.html", 404, titulo="No encontramos lo que buscas", mensaje=mensaje,
                  seccion=None, con_sesion=con_sesion)


@router.get("/ingresar")
def ingresar_form(request: Request, siguiente: str = "/", error: bool = False):
    if not split_csv(get_settings().api_keys):
        return RedirectResponse(_destino_seguro(siguiente), 303)
    return render(request, "ingresar.html", siguiente=_destino_seguro(siguiente), error=error,
                  seccion=None, con_sesion=False)


@router.post("/ingresar")
def ingresar(request: Request, clave: str = Form(...), siguiente: str = Form("/")):
    destino = _destino_seguro(siguiente)
    if not _clave_valida(clave.strip()):
        return RedirectResponse(f"/ingresar?{urlencode({'siguiente': destino, 'error': 1})}", 303)
    r = RedirectResponse(destino, 303)
    r.set_cookie(COOKIE, clave.strip(), httponly=True, samesite="strict",
                 secure=request.url.scheme == "https", max_age=60 * 60 * 24 * 30)
    return r


@router.get("/salir")
def salir():
    r = RedirectResponse("/ingresar", 303)
    r.delete_cookie(COOKIE)
    return r


# ------------------------------------------------------------------------ catálogo
@router.get("/")
def catalogo(request: Request, q: str | None = None, etiqueta: str | None = None,
             con_sesion: bool = Depends(sesion), conn: Connection = Depends(conexion)):
    items = datos.catalogo(conn, q, etiqueta)
    ctx = {"items": items, "q": q or "", "etiqueta": etiqueta}
    if es_htmx(request):
        return render(request, "_tarjetas.html", **ctx)
    return render(request, "catalogo.html", seccion="catalogo", con_sesion=con_sesion,
                  etiquetas=datos.etiquetas(conn), **ctx)


@router.get("/buscar")
def buscar(request: Request, q: str = "", con_sesion: bool = Depends(sesion),
           conn: Connection = Depends(conexion)):
    return render(request, "_buscar.html", q=q, resultados=datos.buscar(conn, q))


# --------------------------------------------------------------------------- ficha
PESTANAS = {"vista": "Vista previa", "columnas": "Columnas", "calidad": "Calidad", "uso": "Cómo usarlo"}


def _contenido_pestana(request: Request, conn: Connection, f: dict[str, Any], pestana: str) -> dict[str, Any]:
    if pestana == "vista":
        return {"tabla": consultas.leer_tabla(conn, f["capa"], f["nombre"], limite=20)}
    if pestana == "columnas":
        return {"perfiles": datos.perfil_columnas(conn, f["capa"], f["nombre"])}
    if pestana == "calidad" and f["fuente"]:
        nombre = f["fuente"]["name"]
        return {"cargas": datos.cargas(conn, nombre), "reglas": datos.reglas_ultima_carga(conn, nombre)}
    return {"base": str(request.base_url).rstrip("/")}


@router.get("/datos/{capa}/{nombre}")
def ficha(request: Request, capa: str, nombre: str, con_sesion: bool = Depends(sesion),
          conn: Connection = Depends(conexion)):
    try:
        f = datos.ficha(conn, capa, nombre)
    except consultas.TablaNoExiste:
        return no_encontrado(request, f"El dataset {capa}.{nombre} no existe o ya no está publicado.", con_sesion)
    pestanas = {k: v for k, v in PESTANAS.items() if k != "calidad" or f["fuente"]}
    return render(request, "ficha.html", seccion="catalogo", con_sesion=con_sesion, f=f, pestanas=pestanas,
                  pestana="vista", **_contenido_pestana(request, conn, f, "vista"))


@router.get("/datos/{capa}/{nombre}/{pestana}")
def ficha_pestana(request: Request, capa: str, nombre: str, pestana: str,
                  con_sesion: bool = Depends(sesion), conn: Connection = Depends(conexion)):
    if pestana not in PESTANAS:
        raise HTTPException(404)
    try:
        f = datos.ficha(conn, capa, nombre)
    except consultas.TablaNoExiste:
        raise HTTPException(404) from None
    if pestana == "calidad" and not f["fuente"]:   # solo las tablas con fuente propia tienen cargas y reglas
        raise HTTPException(404)
    if not es_htmx(request):   # enlace directo a una pestaña: se muestra la ficha completa
        return RedirectResponse(f"/datos/{capa}/{nombre}#{pestana}", 303)
    return render(request, f"_pestana_{pestana}.html", f=f, **_contenido_pestana(request, conn, f, pestana))


# ------------------------------------------------------------------------ explorar
def _estado_explorador(request: Request) -> tuple[list[consultas.Filtro], str | None, int, int]:
    q = request.query_params
    filtros = [consultas.Filtro(c, o, v) for c, o, v in zip(q.getlist("fc"), q.getlist("fo"), q.getlist("fv"),
                                                            strict=False) if c]
    try:
        tamano = int(q.get("n", 50))
        pagina = max(1, int(q.get("p", 1)))
    except ValueError:
        tamano, pagina = 50, 1
    return filtros, q.get("orden") or None, (tamano if tamano in TAMANOS_PAGINA else 50), pagina


def _enlace(request: Request, **cambios: Any) -> str:
    """URL actual del explorador con algunos parámetros cambiados (conserva los filtros)."""
    params = [(k, v) for k, v in request.query_params.multi_items() if k not in cambios]
    params += [(k, v) for k, v in cambios.items() if v not in (None, "")]
    return f"{request.url.path}?{urlencode(params)}" if params else request.url.path


@router.get("/explorar")
def explorar_inicio(request: Request, con_sesion: bool = Depends(sesion), conn: Connection = Depends(conexion)):
    return render(request, "explorar_inicio.html", seccion="explorar", con_sesion=con_sesion,
                  items=datos.catalogo(conn))


@router.get("/explorar/{capa}/{nombre}")
def explorar(request: Request, capa: str, nombre: str, con_sesion: bool = Depends(sesion),
             conn: Connection = Depends(conexion)):
    filtros, orden, tamano, pagina = _estado_explorador(request)
    ctx: dict[str, Any] = {"capa": capa, "nombre": nombre, "filtros": filtros, "orden": orden,
                           "tamano": tamano, "pagina": pagina, "tamanos": TAMANOS_PAGINA,
                           "enlace": lambda **c: _enlace(request, **c), "error": None}
    try:
        ctx["tabla"] = consultas.leer_tabla(conn, capa, nombre, filtros, orden, tamano, (pagina - 1) * tamano)
    except consultas.TablaNoExiste:
        return no_encontrado(request, f"El dataset {capa}.{nombre} no existe o ya no está publicado.", con_sesion)
    except consultas.ConsultaInvalida as e:
        conn.rollback()   # un valor inválido aborta la transacción; las consultas siguientes la necesitan limpia
        ctx["error"], ctx["tabla"] = str(e), None
    ctx["paginas"] = max(1, -(-ctx["tabla"]["total"] // tamano)) if ctx["tabla"] else 1
    ctx["query_csv"] = urlencode([(k, v) for k, v in request.query_params.multi_items() if k not in ("p", "n")])
    if es_htmx(request):
        return render(request, "_resultado.html", **ctx)
    f = datos.ficha(conn, capa, nombre)
    return render(request, "explorar.html", seccion="explorar", con_sesion=con_sesion, f=f,
                  items=datos.catalogo(conn), **ctx)


@router.get("/explorar/{capa}/{nombre}/csv")
def explorar_csv(request: Request, capa: str, nombre: str, sep: str = ",",
                 con_sesion: bool = Depends(sesion), conn: Connection = Depends(conexion)):
    filtros, orden, _, _ = _estado_explorador(request)
    separador = ";" if sep == ";" else ","
    try:
        sql, params, encabezado = consultas.preparar_exportacion(conn, capa, nombre, filtros, orden)
    except consultas.TablaNoExiste:
        raise HTTPException(404) from None
    except consultas.ConsultaInvalida as e:
        return Response(str(e), status_code=400, media_type="text/plain; charset=utf-8")
    sufijo = "_excel" if separador == ";" else ""
    return StreamingResponse(
        consultas.transmitir_csv(conn.engine, sql, params, encabezado, separador),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}{sufijo}.csv"'},
    )


# --------------------------------------------------------------------------- salud
@router.get("/salud")
def salud(request: Request, con_sesion: bool = Depends(sesion), conn: Connection = Depends(conexion)):
    fuentes = datos.salud(conn)
    activas = [f for f in fuentes if f["enabled"]]
    resumen = {
        "total": len(fuentes),
        "al_dia": sum(f["ultimo_estado"] == "success" for f in activas),
        "atencion": sum(f["ultimo_estado"] in ("success_with_warnings", "failed_quality", "failed") for f in activas),
        "deshabilitadas": len(fuentes) - len(activas),
    }
    return render(request, "salud.html", seccion="salud", con_sesion=con_sesion, fuentes=fuentes, resumen=resumen)
