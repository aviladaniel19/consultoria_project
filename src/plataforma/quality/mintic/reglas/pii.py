"""Confidencialidad (ERR018): detección de datos personales.

Reporta la columna y la proporción de valores que coinciden, nunca los valores: el reporte
se guarda en el catálogo y lo ve cualquier persona con acceso a la plataforma.
"""
from __future__ import annotations

import re

import pandas as pd
from pandas.api import types as pdt

from ..modelos import Hallazgo, MetadatosDCAT
from ..util import MUESTRA_PATRONES, en_columna, hallazgo, palabras, textos
from .metadatos import DOMINIOS_PERSONALES

CORREO = re.compile(r"^[\w.+-]+@([\w-]+\.)+[a-z]{2,}$", re.IGNORECASE)
CELULAR = re.compile(r"^(\+?57[\s-]?)?3\d{2}[\s-]?\d{3}[\s-]?\d{4}$")
CEDULA = re.compile(r"^\d{1,3}(\.?\d{3}){1,3}$|^\d{6,10}$")
DIRECCION = re.compile(
    r"^(calle|cll?|carrera|cra|kra?|cr|avenida|av|avda|diagonal|dg|diag|transversal|tv|trans|circular|autopista)"
    r"\.?\s*\d+\s*[a-z]?.{0,25}(#|no\.?|n°|nro\.?|-)\s*\d+", re.IGNORECASE)
NOMBRES_CEDULA = {"cedula", "identificacion", "documento", "nuip", "pasaporte", "cc", "dni"}
NOMBRES_TELEFONO = {"telefono", "celular", "movil", "whatsapp", "tel"}
NOMBRES_PERSONA = {"apellido", "apellidos", "nombres"}
NOMBRES_PERSONA_COMPUESTOS = ({"nombre", "completo"}, {"primer", "nombre"}, {"nombre", "contratista"},
                              {"nombre", "titular"}, {"nombre", "beneficiario"}, {"nombre", "cliente"},
                              {"fecha", "nacimiento"})
UMBRAL = 0.5     # proporción de valores que deben coincidir para marcar la columna


def proporcion(s: pd.Series, patron: re.Pattern[str]) -> float:
    v = textos(s)
    return float(v.map(lambda x: bool(patron.match(x))).mean()) if len(v) else 0.0


def _como_texto(s: pd.Series) -> pd.Series:
    """Valores como texto, también si la columna llegó numérica (una cédula leída como número)."""
    if pdt.is_numeric_dtype(s) and not pdt.is_bool_dtype(s):
        v = s.dropna()
        v = v[v.map(lambda x: float(x).is_integer())].map(lambda x: str(int(x)))
        return v.sample(MUESTRA_PATRONES, random_state=0) if len(v) > MUESTRA_PATRONES else v
    return textos(s)


def datos_personales(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    out = []

    def agregar(c: object, que: str, tasa: float) -> None:
        out.append(hallazgo("ERR018", "error", 3, en_columna(c),
                            f"La columna parece contener {que}.",
                            columna=str(c), afectados=round(tasa * df[c].notna().sum()), tasa=tasa))

    for c in df.columns:
        nombre = palabras(c)
        valores = _como_texto(df[c])
        if valores.empty:
            continue

        def tasa(patron: re.Pattern[str], v: pd.Series = valores) -> float:
            return float(v.map(lambda x: bool(patron.match(x))).mean())

        if nombre & NOMBRES_CEDULA and "nit" not in nombre and tasa(CEDULA) >= UMBRAL:
            agregar(c, "números de identificación de personas", tasa(CEDULA))
        elif (t := tasa(CORREO)) >= UMBRAL:
            personales = float(valores.map(lambda x: x.rsplit("@", 1)[-1].lower() in DOMINIOS_PERSONALES).mean())
            agregar(c, "correos electrónicos personales" if personales >= 0.3 else "correos electrónicos", t)
        elif (t := tasa(CELULAR)) >= UMBRAL or (nombre & NOMBRES_TELEFONO and tasa(re.compile(r"^\+?[\d\s-]{7,13}$"))
                                                >= UMBRAL):
            agregar(c, "números de teléfono", max(t, UMBRAL))
        elif (t := tasa(DIRECCION)) >= 0.3:
            agregar(c, "direcciones exactas", t)
        elif nombre & NOMBRES_PERSONA or any(par <= nombre for par in NOMBRES_PERSONA_COMPUESTOS):
            agregar(c, "nombres u otros datos de personas naturales (por el nombre de la columna)", 1.0)
    return out


REGLAS = [datos_personales]
