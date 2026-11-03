import pandas as pd

from plataforma.quality.contracts import missing_columns, run_checks
from plataforma.quality.profiling import infer_schema, profile
from plataforma.registry.models import Contract

DF = pd.DataFrame({
    "id": ["1", "2", "2", None],
    "precio": ["100", "-5", "30.5", "7"],
    "fecha": ["2026-01-01T00:00:00.000", "2026-01-02T00:00:00.000", None, "2026-01-04T00:00:00.000"],
    "estado": ["Activo", "Activo", "Cerrado", "Otro"],
    "nit": ["900948953", "8001-2", "123", None],
})


def test_inferencia_de_tipos_desde_texto():
    assert infer_schema(DF) == {"estado": "text", "fecha": "datetime", "id": "numeric",
                                "nit": "text", "precio": "numeric"}


def test_perfil_numerico():
    p = {x.column_name: x for x in profile(DF)}["precio"]
    assert p.n == 4 and p.null_rate == 0 and p.min_value == "-5.0"
    assert abs(p.mean - 33.125) < 1e-9 and p.p50 == 18.75


def test_reglas_del_contrato():
    c = Contract.model_validate({
        "required_columns": ["id", "no_existe"],
        "checks": [
            {"column": "id", "rule": "not_null", "severity": "error"},
            {"column": "id", "rule": "unique"},
            {"column": "precio", "rule": "non_negative", "max_failure_rate": 0.3},
            {"column": "precio", "rule": "range", "min": 0, "max": 50},
            {"column": "estado", "rule": "in_set", "values": ["Activo", "Cerrado"]},
            {"column": "nit", "rule": "regex", "pattern": "^[0-9]+$"},
            {"column": "fantasma", "rule": "not_null"},
        ],
    })
    assert missing_columns(DF, c) == ["no_existe"]
    r = {(x.column_name, x.rule): x for x in run_checks(DF, c)}
    assert r[("id", "not_null")].failed == 1 and not r[("id", "not_null")].passed
    assert r[("id", "unique")].failed == 1
    assert r[("precio", "non_negative")].failed == 1 and r[("precio", "non_negative")].passed  # 25% <= 30%
    assert r[("precio", "range")].failed == 2
    assert r[("estado", "in_set")].failed == 1
    assert r[("nit", "regex")].failed == 1
    assert r[("fantasma", "not_null")].failed == 4
