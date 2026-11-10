"""Bitácora de cada dataset: notas sobre los datos, su tratamiento, la limpieza y los cargues.

Leer, cualquier sesión (la pestaña la sirve `rutas.ficha_pestana`). Agregar y editar, quien
puede administrar. Las notas automáticas de cada cargue no se editan.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import Connection

from .. import consultas
from ..storage import catalog
from . import datos
from .carga import admin
from .rutas import conexion, hay_sesion, puede_administrar, render, sesion

router = APIRouter(include_in_schema=False)
MAX_TEXTO, MAX_AUTOR = 4000, 80


def _validar(categoria: str, texto: str, autor: str) -> str | None:
    if categoria not in catalog.CATEGORIAS_BITACORA:
        return "Elige un tipo de nota de la lista."
    if not texto.strip() or not autor.strip():
        return "Escribe la nota y quién la escribe."
    if len(texto) > MAX_TEXTO or len(autor) > MAX_AUTOR:
        return f"La nota admite hasta {MAX_TEXTO} caracteres y el nombre hasta {MAX_AUTOR}."
    return None


@router.post("/datos/{capa}/{nombre}/bitacora")
def agregar(request: Request, capa: str, nombre: str, categoria: str = Form(...), texto: str = Form(...),
            autor: str = Form(...), _a: None = Depends(admin), conn: Connection = Depends(conexion)):
    try:
        f = datos.ficha(conn, capa, nombre)
    except consultas.TablaNoExiste:
        raise HTTPException(404) from None
    error = _validar(categoria, texto, autor)
    valores: dict[str, Any] | None = {"categoria": categoria, "texto": texto, "autor": autor}
    if error is None:
        catalog.agregar_nota(conn, f"{capa}.{nombre}", categoria, texto.strip(), autor.strip())
        conn.commit()
        valores = {"autor": autor.strip()}       # el nombre se conserva para la siguiente nota
    return render(request, "_pestana_bitacora.html", f=f, error=error, valores=valores,
                  notas=datos.notas(conn, f"{capa}.{nombre}"), con_sesion=hay_sesion(request))


@router.get("/bitacora/nota/{nota_id}")
def ver_o_editar(request: Request, nota_id: int, ver: bool = False, _s: bool = Depends(sesion),
                 conn: Connection = Depends(conexion)):
    n = datos.nota(conn, nota_id)
    if n is None:
        raise HTTPException(404)
    if ver or n["automatica"] or not puede_administrar(request):
        return render(request, "_nota.html", n=n)
    return render(request, "_nota_editar.html", n=n, error=None)


@router.post("/bitacora/nota/{nota_id}")
def editar(request: Request, nota_id: int, categoria: str = Form(...), texto: str = Form(...),
           autor: str = Form(...), _a: None = Depends(admin), conn: Connection = Depends(conexion)):
    n = datos.nota(conn, nota_id)
    if n is None or n["automatica"]:
        raise HTTPException(404)
    if error := _validar(categoria, texto, autor):
        return render(request, "_nota_editar.html",
                      n=n | {"categoria": categoria, "texto": texto, "autor": autor}, error=error)
    catalog.editar_nota(conn, nota_id, categoria, texto.strip(), autor.strip())
    conn.commit()
    return render(request, "_nota.html", n=datos.nota(conn, nota_id))
