"""Carga de datos desde la web, sin terminal ni YAML escrito a mano.

Flujo: subir un archivo o conectar una API -> revisar vista previa y columnas -> elegir llave y
columnas obligatorias -> publicar. Publicar escribe `sources/<nombre>.yml` (el registro sigue
siendo la fuente de verdad, versionable en git), lanza la carga en segundo plano y la
publicación automática deja el dataset en el catálogo.
"""
from __future__ import annotations

import csv
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..ingestion.engine import make_extractor
from ..ingestion.file import READERS
from ..publicacion import despublicar, nombre_columna
from ..quality.profiling import infer_schema
from ..registry.loader import RegistryError, load_file
from ..registry.models import SLUG, FileConnection, SourceSpec
from ..seguridad import url_no_permitida
from ..storage import catalog
from ..storage.db import get_engine, quote_ident
from . import tareas
from .rutas import COLOMBIA, es_htmx, hay_sesion, puede_administrar, render, sesion

router = APIRouter(include_in_schema=False)
EXTENSIONES = {".csv": "csv", ".txt": "csv", ".tsv": "csv", ".xlsx": "xlsx", ".json": "json", ".parquet": "parquet"}
TIPOS = {"numeric": "número", "datetime": "fecha", "text": "texto", "boolean": "sí/no",
         "object": "objeto JSON", "unknown": "sin datos"}
SEPARADORES = {",": "coma (,)", ";": "punto y coma (;)", "\t": "tabulador", "|": "barra (|)"}
CODIFICACIONES = {"utf-8-sig": "UTF-8", "latin-1": "Latin-1 (Excel antiguo)"}
# Categorías del Portal Nacional de Datos Abiertos (datos.gov.co)
CATEGORIAS = ["Agricultura y Desarrollo Rural", "Ambiente y Desarrollo Sostenible", "Ciencia, Tecnología e Innovación",
              "Comercio, Industria y Turismo", "Cultura", "Deporte y Recreación", "Economía y Finanzas", "Educación",
              "Estadísticas Nacionales", "Función Pública", "Gastos Gubernamentales", "Hacienda y Crédito Público",
              "Inclusión Social y Reconciliación", "Justicia y Derecho", "Mapas Nacionales", "Minas y Energía",
              "Ordenamiento Territorial", "Organismos de Control", "Participación ciudadana",
              "Presupuestos Gubernamentales", "Salud y Protección Social", "Seguridad y Defensa", "Trabajo",
              "Transporte", "Vivienda, Ciudad y Territorio"]
FRECUENCIAS = ["Diaria", "Semanal", "Quincenal", "Mensual", "Bimestral", "Trimestral", "Cuatrimestral", "Semestral",
               "Anual"]


class SinPermiso(Exception):
    pass


def admin(request: Request, _sesion: bool = Depends(sesion)) -> None:
    if not puede_administrar(request):
        raise SinPermiso


# -------------------------------------------------------------------- utilidades
def _rutas() -> tuple[Path, Path, Path]:
    s = get_settings()
    pendientes = s.landing_dir / ".pendientes"
    pendientes.mkdir(parents=True, exist_ok=True)
    s.sources_dir.mkdir(parents=True, exist_ok=True)
    return s.sources_dir, s.landing_dir, pendientes


def nombre_fuente(titulo: str) -> str:
    n = nombre_columna(titulo, set())
    if n.startswith("c_") or not SLUG.match(n):
        n = f"datos_{n}"[:63]
    return n


def _existe(nombre: str) -> bool:
    return (get_settings().sources_dir / f"{nombre}.yml").exists()


def _pendiente(nombre: str) -> dict[str, Any] | None:
    if not SLUG.match(nombre):
        return None
    ruta = _rutas()[2] / f"{nombre}.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None


def _guardar_subida(archivo: UploadFile, destino: Path) -> bool:
    """Copia el archivo subido respetando PLATAFORMA_MAX_SUBIDA_MB. Escribe primero a un temporal
    en la misma carpeta y solo al final lo pone en su lugar: si se pasa del límite o la subida
    falla, el archivo que había (al reemplazar) queda intacto. Devuelve False si supera el límite."""
    limite, total = get_settings().max_subida_mb * 1024 * 1024, 0
    fd, nombre_tmp = tempfile.mkstemp(dir=destino.parent, prefix=".subida-", suffix=destino.suffix)
    tmp = Path(nombre_tmp)
    try:
        with os.fdopen(fd, "wb") as salida:
            while bloque := archivo.file.read(1024 * 1024):
                total += len(bloque)
                if total > limite:
                    return False
                salida.write(bloque)
        os.replace(tmp, destino)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def _guardar_pendiente(datos: dict[str, Any]) -> None:
    (_rutas()[2] / f"{datos['nombre']}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


def detectar_csv(ruta: Path) -> dict[str, str]:
    """Separador, codificación y separador decimal de un CSV, a partir de sus primeros 64 KB."""
    crudo = ruta.read_bytes()[:65536]
    if len(crudo) == 65536 and b"\n" in crudo:
        crudo = crudo[: crudo.rfind(b"\n") + 1]   # no cortar un carácter de varios bytes
    try:
        texto, codificacion = crudo.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        texto, codificacion = crudo.decode("latin-1"), "latin-1"
    try:
        sep = csv.Sniffer().sniff(texto, delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    opciones = {"sep": sep, "encoding": codificacion}
    if sep == ";" and re.search(r"\d,\d", texto):
        opciones["decimal"] = ","             # típico de Excel con configuración regional de Colombia
    return opciones


def leer_muestra(ruta: Path, formato: str, opciones: dict[str, Any], filas: int = 200) -> list[dict[str, Any]]:
    kwargs = dict(opciones)
    if formato == "csv":
        kwargs["nrows"] = filas
    df = READERS[formato](ruta, **kwargs).head(filas)
    # mismo camino que la ingesta: NaN -> null, fechas -> ISO 8601
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def _spec_api(p: dict[str, Any], max_records: int | None = None) -> SourceSpec:
    return SourceSpec.model_validate(_yaml_fuente(p, {}) | ({"max_records": max_records} if max_records else {}))


def _muestra(p: dict[str, Any]) -> list[dict[str, Any]]:
    if p["tipo"] == "file":
        return leer_muestra(_rutas()[1] / p["archivo"], p["formato"], p["opciones"])
    if motivo := url_no_permitida(p["url"]):    # se resuelve de nuevo: el DNS pudo cambiar
        raise ValueError(motivo)
    spec = _spec_api(p, max_records=50)
    if hasattr(spec.pagination, "page_size"):
        spec = spec.model_copy(update={"pagination": spec.pagination.model_copy(update={"page_size": 50})})
    return next(iter(make_extractor(spec, None).pages()), [])


def _yaml_fuente(p: dict[str, Any], f: dict[str, Any]) -> dict[str, Any]:
    """Configuración de la fuente (lo que se escribe en sources/<nombre>.yml)."""
    d: dict[str, Any] = {"name": p["nombre"], "title": p["titulo"], "description": p["descripcion"] or p["titulo"]}
    if p["etiquetas"]:
        d["tags"] = p["etiquetas"]
    if p["tipo"] == "file":
        d["type"] = "file"
        d["connection"] = {"path": (get_settings().landing_dir / p["archivo"]).as_posix(),
                           "format": p["formato"], "options": p["opciones"]}
    else:
        conn: dict[str, Any] = {"base_url": p["url"]}
        if p.get("ruta_registros"):
            conn["records_path"] = p["ruta_registros"]
        if p.get("auth_header") and p.get("auth_variable"):
            # el secreto nunca se escribe: se lee del entorno (.env); vacío si falta la variable
            conn["auth"] = {"type": "header", "header": p["auth_header"], "value": f"${{{p['auth_variable']}:-}}"}
        d["type"], d["connection"] = "rest", conn
        pag = p.get("paginacion", "none")
        if pag == "offset":
            d["pagination"] = {"type": "offset", "limit_param": p["param_limite"],
                               "offset_param": p["param_desplazamiento"], "page_size": p["tam_pagina"]}
        elif pag == "page":
            d["pagination"] = {"type": "page", "page_param": p["param_pagina"],
                               "size_param": p["param_limite"], "page_size": p["tam_pagina"]}
        if p.get("max_registros"):
            d["max_records"] = p["max_registros"]
        if f.get("cursor"):
            d["incremental"] = {"cursor_field": f["cursor"], "initial_value": f.get("valor_inicial") or ""}
    llave, obligatorias = f.get("llave"), [c for c in f.get("obligatorias", []) if c]
    if llave:
        d["primary_key"] = [llave]
    requeridas = list(dict.fromkeys(([llave] if llave else []) + obligatorias))
    if requeridas:
        checks = []
        if llave:
            checks += [{"column": llave, "rule": "not_null", "severity": "error"},
                       {"column": llave, "rule": "unique", "severity": "warn"}]
        checks += [{"column": c, "rule": "not_null", "severity": "warn"} for c in obligatorias if c != llave]
        d["contract"] = {"required_columns": requeridas, "checks": checks}
    if metadatos := {k: v for k, v in (f.get("metadatos") or {}).items() if v}:
        d["metadata"] = metadatos
    if f.get("vista"):
        d["preview_columns"] = list(f["vista"])
    return d


def _columnas(muestra: list[dict[str, Any]]) -> list[dict[str, str]]:
    orden = list(dict.fromkeys(k for r in muestra for k in r))
    tipos = infer_schema(pd.DataFrame.from_records(muestra)) if muestra else {}
    usados = {"cargado_en", "id_carga"}
    return [{"original": c, "tipo": TIPOS.get(tipos.get(c, "unknown"), "texto"), "publicada": nombre_columna(c, usados)}
            for c in orden]


# ------------------------------------------------------------------ paso 1: origen
@router.get("/cargar")
def cargar(request: Request, _a: None = Depends(admin)):
    return render(request, "cargar.html", seccion="cargar", con_sesion=hay_sesion(request),
                  error=None, en_curso=tareas.en_curso(), max_mb=get_settings().max_subida_mb, valores={})


def _error_inicio(request: Request, mensaje: str, valores: dict[str, Any]):
    return render(request, "cargar.html", 400, seccion="cargar", con_sesion=hay_sesion(request),
                  error=mensaje, en_curso=tareas.en_curso(), max_mb=get_settings().max_subida_mb, valores=valores)


def _etiquetas(texto: str) -> list[str]:
    return [nombre_columna(e, set()).replace("_", "-") for e in texto.split(",") if e.strip()]


@router.post("/cargar/archivo")
def cargar_archivo(request: Request, archivo: UploadFile = File(...), titulo: str = Form(""),
                   descripcion: str = Form(""), etiquetas: str = Form(""), _a: None = Depends(admin)):
    valores = {"titulo": titulo, "descripcion": descripcion, "etiquetas": etiquetas}
    ext = Path(archivo.filename or "").suffix.lower()
    if ext not in EXTENSIONES:
        return _error_inicio(request, "Formato no soportado. Sube un archivo CSV, Excel (.xlsx), JSON o Parquet.", valores)
    titulo = titulo.strip() or Path(archivo.filename).stem.replace("_", " ").replace("-", " ").capitalize()
    nombre = nombre_fuente(titulo)
    if _existe(nombre):
        return _error_inicio(request, f"Ya existe una fuente llamada «{nombre}». Usa otro título, o reemplaza su "
                                      "archivo desde la sección Salud.", valores)
    _, landing, _ = _rutas()
    destino = landing / f"{nombre}{ext}"
    if not _guardar_subida(archivo, destino):
        return _error_inicio(request, f"El archivo supera el máximo de {get_settings().max_subida_mb} MB.", valores)
    formato = EXTENSIONES[ext]
    opciones = detectar_csv(destino) if formato == "csv" else {}
    _guardar_pendiente({"nombre": nombre, "titulo": titulo, "descripcion": descripcion.strip(),
                        "etiquetas": _etiquetas(etiquetas), "tipo": "file", "archivo": destino.name,
                        "formato": formato, "opciones": opciones})
    return RedirectResponse(f"/cargar/revisar/{nombre}", 303)


@router.post("/cargar/api")
def cargar_api(request: Request, titulo: str = Form(...), url: str = Form(...), descripcion: str = Form(""),
               etiquetas: str = Form(""), ruta_registros: str = Form(""), paginacion: str = Form("none"),
               tam_pagina: int = Form(1000), param_limite: str = Form("limit"),
               param_desplazamiento: str = Form("offset"), param_pagina: str = Form("page"),
               max_registros: int = Form(5000), auth_header: str = Form(""), auth_variable: str = Form(""),
               _a: None = Depends(admin)):
    valores = {k: v for k, v in locals().items() if k not in ("request", "_a")}
    if motivo := url_no_permitida(url):
        return _error_inicio(request, motivo, valores)
    if auth_variable and not re.match(r"^[A-Z][A-Z0-9_]*$", auth_variable):
        return _error_inicio(request, "La variable de entorno debe ir en MAYÚSCULAS, con números o guion bajo.", valores)
    nombre = nombre_fuente(titulo)
    if _existe(nombre):
        return _error_inicio(request, f"Ya existe una fuente llamada «{nombre}». Usa otro título.", valores)
    _guardar_pendiente({"nombre": nombre, "titulo": titulo.strip(), "descripcion": descripcion.strip(),
                        "etiquetas": _etiquetas(etiquetas), "tipo": "rest", "url": url.strip(),
                        "ruta_registros": ruta_registros.strip(), "paginacion": paginacion,
                        "tam_pagina": max(1, tam_pagina), "param_limite": param_limite.strip() or "limit",
                        "param_desplazamiento": param_desplazamiento.strip() or "offset",
                        "param_pagina": param_pagina.strip() or "page", "max_registros": max(1, max_registros),
                        "auth_header": auth_header.strip(), "auth_variable": auth_variable.strip()})
    return RedirectResponse(f"/cargar/revisar/{nombre}", 303)


# ----------------------------------------------------------------- paso 2: revisar
@router.get("/cargar/revisar/{nombre}")
def revisar(request: Request, nombre: str, sep: str | None = None, decimal: str | None = None,
            encoding: str | None = None, hoja: str | None = None, _a: None = Depends(admin)):
    p = _pendiente(nombre)
    if p is None:
        return RedirectResponse("/cargar", 303)
    if p["tipo"] == "file" and p["formato"] == "csv" and sep:
        p["opciones"] = {"sep": sep, "encoding": encoding or "utf-8-sig"} | ({"decimal": ","} if decimal == "," else {})
        _guardar_pendiente(p)
    if p["tipo"] == "file" and p["formato"] == "xlsx" and hoja is not None:
        p["opciones"] = {"sheet_name": int(hoja) if hoja.isdigit() else hoja}
        _guardar_pendiente(p)
    return _render_revisar(request, p, error=None)


def _render_revisar(request: Request, p: dict[str, Any], error: str | None, status_code: int = 200):
    muestra, error_lectura = [], None
    try:
        muestra = _muestra(p)
    except Exception as e:  # noqa: BLE001 — cualquier problema de lectura se explica en la página
        error_lectura = f"{type(e).__name__}: {str(e)[:400]}"
    columnas = _columnas(muestra)
    return render(request, "revisar.html", status_code, seccion="cargar",
                  con_sesion=hay_sesion(request), p=p, muestra=muestra[:10],
                  columnas=columnas, error=error, error_lectura=error_lectura,
                  separadores=SEPARADORES, codificaciones=CODIFICACIONES, categorias=CATEGORIAS,
                  frecuencias=FRECUENCIAS)


@router.get("/cargar/cancelar/{nombre}")
def cancelar(nombre: str, _a: None = Depends(admin)):
    p = _pendiente(nombre)
    if p:
        _, landing, pendientes = _rutas()
        if p["tipo"] == "file":
            (landing / p["archivo"]).unlink(missing_ok=True)
        (pendientes / f"{nombre}.json").unlink(missing_ok=True)
    return RedirectResponse("/cargar", 303)


# ---------------------------------------------------------------- paso 3: publicar
@router.post("/cargar/publicar/{nombre}")
def publicar(request: Request, nombre: str, llave: str = Form(""), obligatorias: list[str] = Form([]),
             cursor: str = Form(""), valor_inicial: str = Form(""), vista: list[str] = Form([]),
             col: list[str] = Form([]), desc: list[str] = Form([]), entidad: str = Form(""),
             correo: str = Form(""), categoria: str = Form(""), frecuencia: str = Form(""),
             cobertura: str = Form(""), licencia: str = Form(""), _a: None = Depends(admin)):
    p = _pendiente(nombre)
    if p is None:
        return RedirectResponse("/cargar", 303)
    descripciones = {c: d.strip() for c, d in zip(col, desc, strict=False) if d.strip()}
    # la licencia viene diligenciada por defecto: sola no cuenta como «el usuario llenó los metadatos»
    otros = {"publisher": entidad.strip(), "contact_email": correo.strip(), "category": categoria.strip(),
             "update_frequency": frecuencia.strip(), "coverage": cobertura.strip()}
    metadatos = otros | {"license": licencia.strip() if any(otros.values()) else "",
                         "column_descriptions": descripciones}
    f = {"llave": llave, "obligatorias": obligatorias, "cursor": cursor, "valor_inicial": valor_inicial,
         "vista": vista, "metadatos": metadatos}
    fuentes, _, pendientes = _rutas()
    ruta = fuentes / f"{nombre}.yml"
    if ruta.exists():
        return _render_revisar(request, p, f"Ya existe la fuente «{nombre}».", 400)
    cabecera = (f"# Fuente creada desde la plataforma web el {datetime.now(COLOMBIA):%Y-%m-%d %H:%M}.\n"
                "# Se puede editar a mano: es la configuración de la fuente (ver sources/_plantilla.yml).\n\n")
    ruta.write_text(cabecera + yaml.safe_dump(_yaml_fuente(p, f), sort_keys=False, allow_unicode=True),
                    encoding="utf-8")
    try:
        load_file(ruta)                       # misma validación que `plataforma validate`
    except RegistryError as e:
        ruta.unlink(missing_ok=True)
        return _render_revisar(request, p, f"La configuración no es válida: {e}", 400)
    (pendientes / f"{nombre}.json").unlink(missing_ok=True)
    tareas.lanzar(nombre)
    return RedirectResponse(f"/cargar/progreso/{nombre}", 303)


# --------------------------------------------------------------------- progreso
@router.get("/cargar/progreso/{nombre}")
def progreso(request: Request, nombre: str, _a: None = Depends(admin)):
    t = tareas.estado(nombre)
    if t is None:
        return RedirectResponse(f"/salud#fuente-{nombre}", 303)
    plantilla = "_progreso.html" if es_htmx(request) else "progreso.html"
    return render(request, plantilla, seccion="cargar", con_sesion=hay_sesion(request),
                  t=tareas.resumen(t))


# -------------------------------------------------------- acciones sobre fuentes
def _spec(nombre: str) -> SourceSpec:
    if not SLUG.match(nombre) or not _existe(nombre):
        raise HTTPException(404)
    try:
        return load_file(get_settings().sources_dir / f"{nombre}.yml")
    except RegistryError as e:
        raise HTTPException(400, str(e)) from None


@router.post("/fuentes/{nombre}/actualizar")
def actualizar(nombre: str, _a: None = Depends(admin)):
    _spec(nombre)
    tareas.lanzar(nombre)
    return RedirectResponse(f"/cargar/progreso/{nombre}", 303)


@router.post("/fuentes/{nombre}/archivo")
def reemplazar_archivo(request: Request, nombre: str, archivo: UploadFile = File(...), _a: None = Depends(admin)):
    spec = _spec(nombre)
    if not isinstance(spec.connection, FileConnection):
        raise HTTPException(400, "Solo las fuentes de tipo archivo aceptan un archivo nuevo.")
    landing = get_settings().landing_dir.resolve()
    destino = Path(spec.connection.path).resolve()
    if landing not in destino.parents:        # nunca escribir fuera de la zona de aterrizaje
        raise HTTPException(400, "El archivo de esta fuente no está en la zona de aterrizaje.")
    if Path(archivo.filename or "").suffix.lower() != destino.suffix.lower():
        return render(request, "error.html", 400, titulo="Formato distinto", seccion="salud",
                      con_sesion=hay_sesion(request),
                      mensaje=f"El archivo nuevo debe tener la misma extensión que el original ({destino.suffix}).")
    if nombre in tareas.en_curso():
        raise HTTPException(409, "La fuente se está cargando; espera a que termine.")
    if not _guardar_subida(archivo, destino):
        return render(request, "error.html", 413, titulo="Archivo demasiado grande", seccion="salud",
                      con_sesion=hay_sesion(request),
                      mensaje=f"El archivo supera el máximo de {get_settings().max_subida_mb} MB. "
                              "El archivo anterior se conserva.")
    tareas.lanzar(nombre)
    return RedirectResponse(f"/cargar/progreso/{nombre}", 303)


@router.get("/fuentes/{nombre}/eliminar")
def eliminar_confirmar(request: Request, nombre: str, _a: None = Depends(admin)):
    spec = _spec(nombre)
    return render(request, "eliminar.html", seccion="salud", con_sesion=hay_sesion(request),
                  spec=spec, en_curso=nombre in tareas.en_curso())


@router.post("/fuentes/{nombre}/eliminar")
def eliminar(nombre: str, _a: None = Depends(admin)):
    spec = _spec(nombre)
    if nombre in tareas.en_curso():
        raise HTTPException(409, "La fuente se está cargando; espera a que termine.")
    engine = get_engine()
    despublicar(engine, nombre)
    with engine.begin() as c:
        catalog.eliminar_fuente(c, nombre)
        c.exec_driver_sql(f"DROP TABLE IF EXISTS origen.{quote_ident(spec.origen_table)}")
    if isinstance(spec.connection, FileConnection):
        archivo = Path(spec.connection.path).resolve()
        if get_settings().landing_dir.resolve() in archivo.parents:
            archivo.unlink(missing_ok=True)
    (get_settings().sources_dir / f"{nombre}.yml").unlink(missing_ok=True)
    return RedirectResponse("/salud", 303)
