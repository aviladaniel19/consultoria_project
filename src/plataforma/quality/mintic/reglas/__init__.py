"""Reglas del motor. Cada una es una función `(df, metadatos) -> list[Hallazgo]`; para agregar una,
se escribe en su módulo y se añade a la lista `REGLAS` de ese módulo."""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from ..modelos import Hallazgo, MetadatosDCAT
from . import contenido, estructura, geo, metadatos, pii

Regla = Callable[[pd.DataFrame, MetadatosDCAT], list[Hallazgo]]

REGLAS: list[Regla] = [*metadatos.REGLAS, *estructura.REGLAS, *contenido.REGLAS, *geo.REGLAS, *pii.REGLAS]
