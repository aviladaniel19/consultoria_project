"""Modelo del registro de fuentes.

Cada archivo YAML en `sources/` se valida contra `SourceSpec`. Agregar una
fuente nueva a la plataforma es escribir uno de estos archivos: el motor de
ingesta, el catálogo y la API la descubren solos.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,62}$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- auth
class NoAuth(_Strict):
    type: Literal["none"] = "none"


class HeaderAuth(_Strict):
    type: Literal["header"]
    header: str
    value: str


class BearerAuth(_Strict):
    type: Literal["bearer"]
    token: str


class QueryAuth(_Strict):
    type: Literal["query"]
    param: str
    value: str


Auth = NoAuth | HeaderAuth | BearerAuth | QueryAuth


# --------------------------------------------------------------------- conexiones
class RestConnection(_Strict):
    base_url: str
    method: Literal["GET", "POST"] = "GET"
    auth: Auth = Field(default_factory=NoAuth, discriminator="type")
    params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    records_path: str | None = Field(
        default=None,
        description="Ruta con puntos hasta la lista de registros en la respuesta (p. ej. 'data.items'). "
        "Vacío si la respuesta ya es una lista.",
    )
    timeout_s: float = 60
    max_retries: int = Field(default=3, ge=0, le=10)


class FileConnection(_Strict):
    path: str = Field(description="Ruta local o URL http(s) del archivo")
    format: Literal["csv", "parquet", "json", "xlsx"]
    options: dict[str, Any] = Field(default_factory=dict, description="kwargs para pandas.read_*")


# ---------------------------------------------------------------------- paginación
class NoPagination(_Strict):
    type: Literal["none"] = "none"


class OffsetPagination(_Strict):
    type: Literal["offset"]
    limit_param: str = "limit"
    offset_param: str = "offset"
    page_size: int = Field(default=1000, ge=1, le=100_000)


class PagePagination(_Strict):
    type: Literal["page"]
    page_param: str = "page"
    size_param: str = "page_size"
    page_size: int = Field(default=100, ge=1, le=100_000)
    first_page: int = 1


class CursorPagination(_Strict):
    type: Literal["cursor"]
    cursor_param: str = "cursor"
    next_cursor_path: str = Field(description="Ruta con puntos hasta el siguiente cursor en la respuesta")


Pagination = NoPagination | OffsetPagination | PagePagination | CursorPagination


# --------------------------------------------------------------------- incremental
class IncrementalFilter(_Strict):
    param: str = Field(description="Parámetro de la API donde va el filtro")
    template: str = Field(description="Plantilla con {field} y {value}")


class Incremental(_Strict):
    cursor_field: str
    initial_value: str
    filter: IncrementalFilter | None = Field(
        default=None,
        description="Cómo empujar el filtro a la API. Si se omite, se filtra en Python tras extraer.",
    )


# ------------------------------------------------------------------------ contrato
CheckRule = Literal["not_null", "unique", "non_negative", "range", "in_set", "regex"]


class Check(_Strict):
    column: str
    rule: CheckRule
    min: float | None = None
    max: float | None = None
    values: list[Any] | None = None
    pattern: str | None = None
    severity: Literal["warn", "error"] = "warn"
    max_failure_rate: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def _args_por_regla(self) -> "Check":
        if self.rule == "range" and self.min is None and self.max is None:
            raise ValueError("la regla 'range' necesita 'min' y/o 'max'")
        if self.rule == "in_set" and not self.values:
            raise ValueError("la regla 'in_set' necesita 'values'")
        if self.rule == "regex" and not self.pattern:
            raise ValueError("la regla 'regex' necesita 'pattern'")
        return self


class Contract(_Strict):
    required_columns: list[str] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    on_schema_change: Literal["record", "fail"] = "record"


# -------------------------------------------------------------------------- fuente
class SourceSpec(_Strict):
    name: str = Field(description="Identificador único: minúsculas, números y guion bajo")
    description: str
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    type: Literal["rest", "file"]
    schedule: str | None = Field(default=None, description="Cron informativo para el orquestador")
    connection: RestConnection | FileConnection
    pagination: Pagination = Field(default_factory=NoPagination, discriminator="type")
    max_records: int | None = Field(default=None, ge=1, description="Tope por ejecución")
    incremental: Incremental | None = None
    primary_key: list[str] = Field(default_factory=list)
    contract: Contract = Field(default_factory=Contract)

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG.match(v):
            raise ValueError("debe empezar por letra y usar solo [a-z0-9_], máx. 63 caracteres")
        return v

    @model_validator(mode="before")
    @classmethod
    def _conexion_por_tipo(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("connection"), dict):
            conn = data["connection"]
            model = RestConnection if data.get("type") == "rest" else FileConnection
            data = {**data, "connection": model.model_validate(conn)}
        return data

    @model_validator(mode="after")
    def _coherencia(self) -> "SourceSpec":
        if self.type == "file" and not isinstance(self.pagination, NoPagination):
            raise ValueError("las fuentes 'file' no usan paginación")
        if self.type == "file" and self.incremental and self.incremental.filter:
            raise ValueError("en fuentes 'file' el incremental se filtra en Python: omite 'filter'")
        return self

    @property
    def origen_table(self) -> str:
        return self.name
