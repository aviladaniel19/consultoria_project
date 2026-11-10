from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from plataforma.api.main import require_key
from plataforma.config import get_settings, split_csv
from plataforma.seguridad import intentos_clave

PETICION = SimpleNamespace(client=SimpleNamespace(host="10.0.0.9"))


@pytest.fixture
def claves(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_keys", "clave-docentes, clave-estudiantes")
    intentos_clave.reiniciar()
    yield
    intentos_clave.reiniciar()


def test_split_csv():
    assert split_csv(" a, ,b ,") == ["a", "b"] and split_csv("") == []


def test_sin_claves_la_api_queda_abierta(monkeypatch):
    monkeypatch.setattr(get_settings(), "api_keys", "")
    assert require_key(PETICION, None) is None


def test_acepta_cualquiera_de_las_claves(claves):
    assert require_key(PETICION, "clave-docentes") is None and require_key(PETICION, "clave-estudiantes") is None


@pytest.mark.parametrize("clave", [None, "", "otra", "clave-docentes "])
def test_rechaza_clave_ausente_o_invalida(claves, clave):
    with pytest.raises(HTTPException) as e:
        require_key(PETICION, clave)
    assert e.value.status_code == 401


def test_bloquea_tras_varias_claves_incorrectas(claves):
    for _ in range(10):
        with pytest.raises(HTTPException):
            require_key(PETICION, "adivinando")
    with pytest.raises(HTTPException) as e:
        require_key(PETICION, "clave-docentes")       # ni la correcta, mientras dure el bloqueo
    assert e.value.status_code == 429 and int(e.value.headers["Retry-After"]) > 0


@pytest.mark.parametrize("sql", ["DELETE FROM analitico.demo", "SELECT 1; DROP TABLE x", "drop table x",
                                 "update t set a = 1"])
def test_mcp_rechaza_consultas_que_no_son_select(sql):
    pytest.importorskip("mcp")
    from plataforma.mcp_server import _consulta

    with pytest.raises(ValueError):
        _consulta(None, sql)          # se rechaza antes de tocar la base de datos
