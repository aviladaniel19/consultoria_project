"""Georreferenciación: dirección sin coordenadas (ERR009) y coordenadas fuera de Colombia."""
from __future__ import annotations

import pandas as pd

from ..modelos import Hallazgo, MetadatosDCAT
from ..util import a_numero, en_columna, hallazgo, palabras
from .pii import DIRECCION, proporcion

# Caja que contiene el territorio continental e insular de Colombia.
LATITUD, LONGITUD = (-4.3, 13.5), (-79.0, -66.8)
NOMBRES_LAT = {"lat", "latitud", "latitude"}
NOMBRES_LON = {"lon", "lng", "long", "longitud", "longitude"}
NOMBRES_DIRECCION = {"direccion", "address", "domicilio"}


def columnas_geo(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    lat = [c for c in df.columns if palabras(c) & NOMBRES_LAT]
    lon = [c for c in df.columns if palabras(c) & NOMBRES_LON and c not in lat]
    return lat, lon


def direccion_sin_coordenadas(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR009: si hay un campo de dirección, deben existir latitud y longitud."""
    lat, lon = columnas_geo(df)
    if lat and lon:
        return []
    for c in df.columns:
        if palabras(c) & NOMBRES_DIRECCION or proporcion(df[c], DIRECCION) >= 0.3:
            return [hallazgo("ERR009", "advertencia", 3, en_columna(c),
                             "Hay un campo de dirección y el conjunto no tiene columnas de latitud y longitud.",
                             columna=str(c))]
    return []


def coordenadas_en_colombia(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """Latitud entre -4,3 y 13,5 y longitud entre -79,0 y -66,8."""
    out = []
    lat, lon = columnas_geo(df)
    for cols, (minimo, maximo), (omin, omax), nombre in ((lat, LATITUD, LONGITUD, "latitud"),
                                                        (lon, LONGITUD, LATITUD, "longitud")):
        for c in cols:
            x = a_numero(df[c]).dropna()
            if x.empty:
                continue
            fuera = x[(x < minimo) | (x > maximo)]
            if fuera.empty:
                continue
            invertidas = bool(((fuera >= omin) & (fuera <= omax)).mean() > 0.8)
            detalle = " Parecen intercambiadas con la otra coordenada." if invertidas else ""
            out.append(hallazgo("PD-GEO-RANGO", "advertencia", max(1.0, 5 * len(fuera) / len(x)), en_columna(c),
                                f"{len(fuera)} valores de {nombre} están fuera del rango de Colombia "
                                f"({minimo} a {maximo}).{detalle}", columna=str(c), afectados=len(fuera),
                                tasa=len(fuera) / len(x)))
    return out


REGLAS = [direccion_sin_coordenadas, coordenadas_en_colombia]
