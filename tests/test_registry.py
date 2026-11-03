from pathlib import Path

import pytest

from plataforma.registry.loader import RegistryError, load_file, load_registry
from plataforma.registry.models import OffsetPagination, RestConnection

ROOT = Path(__file__).resolve().parents[1]

MIN_REST = """
name: {name}
description: prueba
type: rest
connection:
  base_url: https://api.ejemplo.com/items
  auth: {{type: bearer, token: "${{TOKEN_PRUEBA}}"}}
"""


def write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / f"{name}.yml"
    p.write_text(body, encoding="utf-8")
    return p


def test_registro_del_repo_es_valido():
    reg = load_registry(ROOT / "sources")
    assert "secop_procesos" in reg
    spec = reg["secop_procesos"].spec
    assert isinstance(spec.connection, RestConnection)
    assert isinstance(spec.pagination, OffsetPagination)
    assert spec.pagination.limit_param == "$limit"
    assert reg["ejemplo_archivo"].spec.enabled is False


def test_ignora_plantillas(tmp_path):
    write(tmp_path, "_borrador", "esto: [no es valido")
    assert load_registry(tmp_path) == {}


def test_interpola_variables(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_PRUEBA", "abc")
    spec = load_file(write(tmp_path, "api_x", MIN_REST.format(name="api_x")))
    assert spec.connection.auth.token == "abc"


def test_falla_si_falta_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("TOKEN_PRUEBA", raising=False)
    with pytest.raises(RegistryError, match="TOKEN_PRUEBA"):
        load_file(write(tmp_path, "api_x", MIN_REST.format(name="api_x")))


def test_nombre_debe_coincidir_con_archivo(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_PRUEBA", "abc")
    with pytest.raises(RegistryError, match="coincidir"):
        load_file(write(tmp_path, "otro", MIN_REST.format(name="api_x")))


def test_regla_range_exige_limites(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKEN_PRUEBA", "abc")
    body = MIN_REST.format(name="api_x") + "contract:\n  checks:\n    - {column: v, rule: range}\n"
    with pytest.raises(RegistryError, match="range"):
        load_file(write(tmp_path, "api_x", body))


def test_archivo_no_acepta_paginacion(tmp_path):
    body = """
name: archivo_f
description: x
type: file
connection: {path: a.csv, format: csv}
pagination: {type: offset}
"""
    with pytest.raises(RegistryError, match="paginación"):
        load_file(write(tmp_path, "archivo_f", body))


def test_errores_se_acumulan(tmp_path):
    write(tmp_path, "a", "name: a\ndescription: x\ntype: rest\n")
    write(tmp_path, "b", "name: B\ndescription: x\ntype: rest\nconnection: {base_url: u}\n")
    with pytest.raises(RegistryError) as e:
        load_registry(tmp_path)
    assert "a.yml" in str(e.value) and "b.yml" in str(e.value)
