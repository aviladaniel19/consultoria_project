"""Reglas de estructura y volumen (ERR004, ERR005, ERR008, ERR008_1, ERR008_2, ERR011, ERR016)."""
from __future__ import annotations

import re

import pandas as pd

from ..modelos import Hallazgo, MetadatosDCAT
from ..util import en_columna, es_texto, hallazgo, palabras, sin_tildes, textos, tipo
from .metadatos import VIGENCIA

FILAS_MINIMAS, COLUMNAS_MINIMAS = 50, 5
SIN_NOMBRE = re.compile(r"^(unnamed.*|column_?\d*|columna_?\d*|col_?\d+|field_?\d+|campo_?\d+|_c\d+|\d+|)$")
TOTAL = re.compile(r"^(sub)?total(es)?( general| nacional| departamental)?:?$")
PERIODO = {"vigencia", "anio", "ano", "year", "periodo", "fecha", "mes", "trimestre", "semestre"}


def volumen(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR004, ERR005, ERR008 y ERR008_1."""
    filas, columnas = df.shape
    out = []
    if filas == 0:
        out.append(hallazgo("ERR004", "error", 10, "conjunto", "El conjunto no tiene filas con información.",
                            bloqueante=True))
    elif filas < FILAS_MINIMAS:
        out.append(hallazgo("ERR005", "advertencia", 4, "conjunto",
                            f"El conjunto tiene {filas} filas; con menos de {FILAS_MINIMAS} no permite la "
                            "reutilización.", afectados=filas))
    if columnas <= 1:
        out.append(hallazgo("ERR008", "error", 10, "conjunto", "El conjunto tiene una sola columna.",
                            bloqueante=True))
    elif columnas < COLUMNAS_MINIMAS:
        out.append(hallazgo("ERR008_1", "advertencia", 3, "conjunto",
                            f"El conjunto tiene {columnas} columnas; se esperan al menos {COLUMNAS_MINIMAS}.",
                            afectados=columnas))
    return out


def columnas_sin_nombre(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR008_2: columnas sin nombre o con el nombre por defecto (Unnamed, Column1…)."""
    return [hallazgo("ERR008_2", "advertencia", 10 / len(df.columns), en_columna(c),
                     "La columna no tiene nombre o conserva uno por defecto.", columna=str(c))
            for c in df.columns if SIN_NOMBRE.match(sin_tildes(c).strip())]


def consolidacion_historica(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR011: un conjunto por vigencia, sin columna de periodo, debería consolidarse en uno solo."""
    if not VIGENCIA.search(m.titulo):
        return []
    hay_periodo = any(palabras(c) & PERIODO or tipo(df[c]) == "datetime" for c in df.columns)
    if hay_periodo:
        return []
    return [hallazgo("ERR011", "advertencia", 3, "conjunto",
                     "El título indica una vigencia y no hay una columna de periodo: parece un conjunto "
                     "fragmentado por años.")]


def filas_totalizadas(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR016: filas de totales o subtotales mezcladas con el detalle."""
    if df.empty:
        return []
    marcadas = pd.Series(False, index=df.index)
    for c in df.columns:
        if es_texto(df[c]):
            v = textos(df[c], limite=len(df))
            marcadas.loc[v.index[v.map(lambda x: bool(TOTAL.match(sin_tildes(x).strip())))]] = True
    n = int(marcadas.sum())
    if not n:
        return []
    return [hallazgo("ERR016", "advertencia", max(2.0, 10 * n / len(df)), "conjunto",
                     f"{n} filas son totales o subtotales: los datos deben publicarse en su máximo nivel de "
                     "desagregación.", afectados=n, tasa=n / len(df))]


REGLAS = [volumen, columnas_sin_nombre, consolidacion_historica, filas_totalizadas]
