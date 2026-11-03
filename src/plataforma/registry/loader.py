"""Carga y valida el registro de fuentes (`sources/*.yml`).

- Los archivos que empiezan por `_` se ignoran (plantillas, borradores).
- `${VAR}` y `${VAR:-defecto}` se reemplazan con variables de entorno, así los
  secretos nunca quedan en el repositorio.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import SourceSpec

ENV_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


class RegistryError(Exception):
    pass


@dataclass(frozen=True)
class LoadedSource:
    spec: SourceSpec
    path: Path


def _interpolate(text: str, path: Path) -> str:
    def repl(m: re.Match[str]) -> str:
        var, default = m.group(1), m.group(2)
        val = os.environ.get(var)
        if val is None or val == "":
            if default is not None:
                return default
            raise RegistryError(f"{path.name}: falta la variable de entorno {var}")
        return val

    return ENV_VAR.sub(repl, text)


def load_file(path: Path) -> SourceSpec:
    raw = yaml.safe_load(_interpolate(path.read_text(encoding="utf-8"), path))
    if not isinstance(raw, dict):
        raise RegistryError(f"{path.name}: el YAML debe ser un mapa")
    try:
        spec = SourceSpec.model_validate(raw)
    except ValidationError as e:
        errores = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise RegistryError(f"{path.name}: {errores}") from None
    if spec.name != path.stem:
        raise RegistryError(f"{path.name}: 'name' ({spec.name}) debe coincidir con el nombre del archivo")
    return spec


def load_registry(directory: Path, only_enabled: bool = False) -> dict[str, LoadedSource]:
    if not directory.is_dir():
        raise RegistryError(f"no existe el directorio de fuentes: {directory}")
    sources: dict[str, LoadedSource] = {}
    errors: list[str] = []
    for path in sorted(directory.glob("*.y*ml")):
        if path.name.startswith("_"):
            continue
        try:
            spec = load_file(path)
        except RegistryError as e:
            errors.append(str(e))
            continue
        if only_enabled and not spec.enabled:
            continue
        sources[spec.name] = LoadedSource(spec, path)
    if errors:
        raise RegistryError("registro inválido:\n  - " + "\n  - ".join(errors))
    return sources
