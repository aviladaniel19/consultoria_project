"""Utilidades compartidas por las reglas."""
from __future__ import annotations

import json
import re
import unicodedata

import pandas as pd
from pandas.api import types as pdt

from ..profiling import as_numeric, infer_type
from .catalogo import ERRORES
from .modelos import Hallazgo, Severidad

MUESTRA_PATRONES = 20_000   # filas que revisan las reglas de patrones (regex) en columnas muy largas


def hallazgo(codigo: str, severidad: Severidad, penalizacion: float, ubicacion: str, mensaje: str, *,
             columna: str | None = None, afectados: int = 0, tasa: float | None = None,
             bloqueante: bool = False) -> Hallazgo:
    error = ERRORES[codigo]
    return Hallazgo(codigo=codigo, criterio=error.criterio, severidad=severidad, ubicacion=ubicacion,
                    columna=columna, mensaje=mensaje, recomendacion=error.recomendacion, afectados=afectados,
                    tasa=None if tasa is None else round(tasa, 6),
                    penalizacion=round(max(0.0, min(10.0, penalizacion)), 4), bloqueante=bloqueante)


def miles(n: float, decimales: int = 0) -> str:
    """Formato de Colombia: 7.562 y 73,1."""
    return f"{n:,.{decimales}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def en_columna(col: object) -> str:
    return f"columna «{col}»"


def sin_tildes(texto: object) -> str:
    s = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def palabras(nombre: object) -> set[str]:
    """'Fecha_Creación Proceso' -> {'fecha', 'creacion', 'proceso'}"""
    return set(re.findall(r"[a-z]+|[0-9]+", sin_tildes(nombre)))


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Copia con las celdas no comparables (dict, list) como texto, para poder contar duplicados."""
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object and df[c].map(lambda v: isinstance(v, (dict, list))).any():
            df[c] = df[c].map(lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False)
                              if isinstance(v, (dict, list)) else v)
    return df


def tipo(s: pd.Series) -> str:
    """Tipo de la columna: el de la base de datos si ya viene tipada, o el inferido de sus valores."""
    if pdt.is_bool_dtype(s):
        return "boolean"
    if pdt.is_datetime64_any_dtype(s):
        return "datetime"
    if pdt.is_numeric_dtype(s):
        return "numeric"
    return infer_type(s)


def es_texto(s: pd.Series) -> bool:
    return s.dtype == object or pdt.is_string_dtype(s)


def textos(s: pd.Series, limite: int = MUESTRA_PATRONES) -> pd.Series:
    """Valores de texto no vacíos de la columna (una muestra fija si es muy larga)."""
    if not es_texto(s):
        return pd.Series([], dtype="string")
    v = s.dropna().map(lambda x: x if isinstance(x, str) else str(x)).astype("string").str.strip()
    v = v[v != ""]
    return v.sample(limite, random_state=0) if len(v) > limite else v


def a_numero(s: pd.Series) -> pd.Series:
    """Convierte a número aceptando coma decimal ('-75,58')."""
    if pdt.is_numeric_dtype(s) and not pdt.is_bool_dtype(s):
        return s.astype("float64")
    return as_numeric(s.map(lambda v: v.strip().replace(",", ".") if isinstance(v, str) else v))
