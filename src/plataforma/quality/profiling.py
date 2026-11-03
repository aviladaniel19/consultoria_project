"""Inferencia de tipos y perfilado estadístico por columna.

Las APIs abiertas (Socrata incluido) suelen devolver números y fechas como
texto, así que el tipo se infiere por la proporción de valores convertibles.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

TYPE_THRESHOLD = 0.98  # fracción mínima de valores no nulos convertibles para asignar el tipo


def _hashable(s: pd.Series) -> pd.Series:
    return s.map(lambda v: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v)


def as_numeric(s: pd.Series) -> pd.Series:
    if s.map(lambda v: isinstance(v, (dict, list, bool))).any():
        return pd.Series(np.nan, index=s.index)
    return pd.to_numeric(s, errors="coerce")


def as_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype("string"), errors="coerce", format="ISO8601", utc=True)


def infer_type(s: pd.Series) -> str:
    v = s.dropna()
    if v.empty:
        return "unknown"
    if v.map(lambda x: isinstance(x, (dict, list))).any():
        return "object"
    if v.map(lambda x: isinstance(x, bool)).all():
        return "boolean"
    if as_numeric(v).notna().mean() >= TYPE_THRESHOLD:
        return "numeric"
    if v.map(lambda x: isinstance(x, str) and len(x) >= 8).all() and as_datetime(v).notna().mean() >= TYPE_THRESHOLD:
        return "datetime"
    return "text"


def infer_schema(df: pd.DataFrame) -> dict[str, str]:
    return {c: infer_type(df[c]) for c in sorted(df.columns)}


@dataclass
class ColumnProfile:
    column_name: str
    inferred_type: str
    n: int
    null_rate: float
    n_distinct: int
    min_value: str | None = None
    max_value: str | None = None
    mean: float | None = None
    std: float | None = None
    p50: float | None = None

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


def _f(x: Any) -> float | None:
    return None if x is None or pd.isna(x) else float(x)


def profile_column(name: str, s: pd.Series, inferred: str) -> ColumnProfile:
    n = len(s)
    p = ColumnProfile(
        column_name=name,
        inferred_type=inferred,
        n=n,
        null_rate=float(s.isna().mean()) if n else 0.0,
        n_distinct=int(_hashable(s).nunique(dropna=True)),
    )
    if inferred == "numeric":
        x = as_numeric(s).dropna()
        if not x.empty:
            p.min_value, p.max_value = repr(_f(x.min())), repr(_f(x.max()))
            p.mean, p.p50 = _f(x.mean()), _f(x.median())
            p.std = _f(x.std(ddof=1)) if len(x) > 1 else None
    elif inferred == "datetime":
        t = as_datetime(s).dropna()
        if not t.empty:
            p.min_value, p.max_value = t.min().isoformat(), t.max().isoformat()
    return p


def profile(df: pd.DataFrame, schema: dict[str, str] | None = None) -> list[ColumnProfile]:
    schema = schema or infer_schema(df)
    return [profile_column(c, df[c], schema[c]) for c in schema]
