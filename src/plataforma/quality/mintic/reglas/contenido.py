"""Reglas sobre filas y columnas: completitud (ERR007), tipos (ERR019), unicidad (ERR020) y las
comprobaciones propias de columnas redundantes y constantes."""
from __future__ import annotations

import re

import pandas as pd

from ...profiling import as_datetime, as_numeric
from ..modelos import Hallazgo, MetadatosDCAT
from ..util import en_columna, es_texto, hallazgo, miles, palabras, sin_tildes, textos

# Rellenos que equivalen a «sin dato» y que conviene estandarizar (vacío o «No aplica»).
RELLENOS = {"n/a", "na", "n.a.", "n.a", "nd", "n/d", "s/d", "s/i", "sd", "sin dato", "sin datos", "sin informacion",
            "sin info", "ninguno", "ninguna", "null", "none", "nan", "nulo", "-", "--", "---", ".", "..", "?", "??",
            "no registra", "no reporta", "no informa", "no definido", "por definir", "pendiente", "vacio", "#n/a"}
FICTICIO_TEXTO = re.compile(r"^(x{3,}|z{3,}|a{4,}|0{4,}|9{5,}|1234\d*|abc\w{0,3}|test\w*|prueba\w*|dummy|ejemplo|"
                            r"asdf\w*|qwerty|lorem ipsum.*|fulano.*|foo|bar)$")
FICTICIO_NUMERO = re.compile(r"^(123456\d*|(\d)\2{5,}|987654\d*)$")
COMA_DECIMAL = re.compile(r"^-?(\d{1,3}(\.\d{3})+|\d+),\d+$")
FECHA_NO_ISO = re.compile(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(\s+\d{1,2}:\d{2}(:\d{2})?)?$")
IDENTIFICADORES = {"id", "identificacion", "cedula", "documento", "nit", "telefono", "celular", "codigo"}
UMBRAL_TIPO = 0.8     # proporción de valores de un tipo para considerarlo el tipo de la columna


def _celdas(df: pd.DataFrame) -> int:
    return max(1, df.shape[0] * df.shape[1])


def _es_relleno(v: object) -> bool:
    return isinstance(v, str) and sin_tildes(v).strip() in RELLENOS


def completitud(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR007: celdas vacías y rellenos no estandarizados, por columna."""
    out = []
    for c in df.columns:
        s = df[c]
        vacias = int(s.isna().sum())
        rellenos = 0
        if es_texto(s):
            vacias += int(s.map(lambda v: isinstance(v, str) and not v.strip()).sum())
            rellenos = int(s.map(_es_relleno).sum())
        if not (vacias or rellenos):
            continue
        partes = [f"{miles(vacias)} celdas vacías"] if vacias else []
        if rellenos:
            partes.append(f"{miles(rellenos)} con rellenos como «N/A» o «-» (estandarizar: vacío o «No aplica»)")
        out.append(hallazgo("ERR007", "advertencia", 10 * (vacias + rellenos) / _celdas(df), en_columna(c),
                            "La columna tiene " + " y ".join(partes) + ".", columna=str(c),
                            afectados=vacias + rellenos, tasa=(vacias + rellenos) / len(df)))
    return out


def tipos_de_datos(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR019: valores que no corresponden al tipo de su columna, formatos no estándar y datos ficticios."""
    out = []

    def agregar(c: object, mensaje: str, afectados: int, total: int) -> None:
        out.append(hallazgo("ERR019", "advertencia", max(0.5, 10 * afectados / _celdas(df)), en_columna(c),
                            mensaje, columna=str(c), afectados=afectados, tasa=afectados / max(1, total)))

    for c in df.columns:
        s = df[c]
        if es_texto(s):
            v = textos(s)
            v = v[~v.map(_es_relleno)]
            if v.empty:
                continue
            ficticios = int(v.map(lambda x: bool(FICTICIO_TEXTO.match(sin_tildes(x)))).sum())
            if ficticios:
                agregar(c, f"{miles(ficticios)} valores parecen datos ficticios o de prueba (XXXXX, 1234, test…).",
                        ficticios, len(v))
            numericos = as_numeric(v).notna().mean()
            con_coma = v.map(lambda x: bool(COMA_DECIMAL.match(x))).mean()
            fechas_iso = as_datetime(v).notna().mean() if v.str.len().min() >= 8 else 0.0
            fechas_otras = v.map(lambda x: bool(FECHA_NO_ISO.match(x))).mean()
            if UMBRAL_TIPO <= numericos < 1:
                malos = round((1 - numericos) * len(v))
                agregar(c, f"La columna es numérica, pero {miles(malos)} valores no son números.", malos, len(v))
            elif con_coma >= UMBRAL_TIPO:
                agregar(c, "Los números están publicados como texto con coma decimal; deben ser numéricos con "
                           "punto decimal.", round(con_coma * len(v)), len(v))
            elif fechas_otras >= UMBRAL_TIPO:
                agregar(c, "Las fechas no siguen el formato ISO 8601 (AAAA-MM-DD).",
                        round(fechas_otras * len(v)), len(v))
            elif UMBRAL_TIPO <= fechas_iso < 1:
                malos = round((1 - fechas_iso) * len(v))
                agregar(c, f"La columna es de fechas, pero {miles(malos)} valores no son fechas válidas.", malos, len(v))
        elif palabras(c) & IDENTIFICADORES and pd.api.types.is_numeric_dtype(s):
            v = s.dropna()
            ficticios = int(v.map(lambda x: bool(FICTICIO_NUMERO.match(str(int(x)))) if float(x).is_integer()
                                  else False).sum())
            if ficticios:
                agregar(c, f"{miles(ficticios)} identificadores parecen ficticios (123456, 999999…).", ficticios, len(v))
    return out


def unicidad(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """ERR020: filas completas repetidas e identificadores repetidos."""
    if df.empty:
        return []
    out = []
    filas = int(df.duplicated().sum())
    if filas:
        out.append(hallazgo("ERR020", "advertencia", max(1.0, 10 * filas / len(df)), "conjunto",
                            f"{miles(filas)} filas son copias exactas de otra.", afectados=filas, tasa=filas / len(df)))
    llave = [c for c in m.llave if c in df.columns]
    if llave and len(llave) == len(m.llave):
        con_llave = df.dropna(subset=llave)
        ids = int(con_llave.duplicated(subset=llave).sum()) - filas
        if ids > 0:
            out.append(hallazgo("ERR020", "advertencia", max(1.0, 10 * ids / len(df)),
                                en_columna(", ".join(llave)),
                                f"{miles(ids)} filas repiten el identificador de otra fila con datos distintos.",
                                columna=llave[0], afectados=ids, tasa=ids / len(df)))
    return out


def columnas_redundantes(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """Columnas con distinto nombre y exactamente el mismo contenido (p. ej. municipio y municipio_nombre)."""
    if len(df) < 2:
        return []
    grupos: dict[int, list[str]] = {}
    for c in df.columns:
        s = df[c]
        if s.nunique(dropna=True) <= 1:          # las constantes se reportan aparte
            continue
        texto = s.map(lambda v: "" if pd.isna(v) else str(v).strip())
        grupos.setdefault(int(pd.util.hash_pandas_object(texto, index=False).sum()), []).append(c)
    out = []
    for cols in grupos.values():
        primera = cols[0]
        base = df[primera].map(lambda v: "" if pd.isna(v) else str(v).strip())
        for otra in cols[1:]:
            if base.equals(df[otra].map(lambda v: "" if pd.isna(v) else str(v).strip())):
                out.append(hallazgo("PD-COL-REDUNDANTE", "info", 10 / len(df.columns), en_columna(otra),
                                    f"Tiene exactamente el mismo contenido que «{primera}».", columna=str(otra),
                                    afectados=1))
    return out


def columnas_constantes(df: pd.DataFrame, m: MetadatosDCAT) -> list[Hallazgo]:
    """Columnas con un único valor en el 100 % de los registros: no aportan variabilidad."""
    if len(df) < 2:
        return []
    return [hallazgo("PD-COL-CONSTANTE", "info", 10 / len(df.columns), en_columna(c),
                     "Todos los registros tienen el mismo valor.", columna=str(c), afectados=len(df), tasa=1.0)
            for c in df.columns if df[c].notna().all() and df[c].nunique() == 1]


REGLAS = [completitud, tipos_de_datos, unicidad, columnas_redundantes, columnas_constantes]
