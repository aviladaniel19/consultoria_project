"""Extractor de archivos (local o URL) apoyado en pandas."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pandas as pd

from ..registry.models import FileConnection, SourceSpec

READERS = {
    "csv": pd.read_csv,
    "parquet": pd.read_parquet,
    "json": pd.read_json,
    "xlsx": pd.read_excel,
}


class FileExtractor:
    chunk_size = 5000

    def __init__(self, spec: SourceSpec, cursor_value: str | None = None):
        if not isinstance(spec.connection, FileConnection):
            raise TypeError("FileExtractor requiere una conexión de archivo")
        self.spec = spec
        self.conn: FileConnection = spec.connection

    def pages(self) -> Iterator[list[dict[str, Any]]]:
        df = READERS[self.conn.format](self.conn.path, **self.conn.options)
        if self.spec.max_records:
            df = df.head(self.spec.max_records)
        # to_json -> json.loads convierte NaN en null y fechas en ISO 8601: JSON listo para JSONB
        for start in range(0, len(df), self.chunk_size):
            chunk = df.iloc[start : start + self.chunk_size]
            yield json.loads(chunk.to_json(orient="records", date_format="iso", force_ascii=False))
