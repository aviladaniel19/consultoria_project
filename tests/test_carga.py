from pathlib import Path

import pytest

from plataforma.publicacion import nombre_columna
from plataforma.registry.models import SourceSpec
from plataforma.web.carga import _yaml_fuente, detectar_csv, leer_muestra, nombre_fuente

EJEMPLOS = Path(__file__).resolve().parents[1] / "ejemplos"


def test_nombre_de_columna_limpio_y_sin_repetir():
    usados = {"cargado_en"}
    assert nombre_columna("Largo del sépalo (cm)", usados) == "largo_del_sepalo_cm"
    assert nombre_columna("largo del sépalo cm", usados) == "largo_del_sepalo_cm_2"
    assert nombre_columna("2024", usados) == "c_2024"
    assert nombre_columna("cargado_en", usados) == "cargado_en_2"     # reservada por la plataforma
    assert nombre_columna("¿¡!?", usados) == "columna"


def test_nombre_de_fuente_valido():
    assert nombre_fuente("Municipios de Colombia (DIVIPOLA)") == "municipios_de_colombia_divipola"
    assert nombre_fuente("2026 matrículas") == "datos_c_2026_matriculas"


def test_detecta_formato_de_excel_colombiano():
    assert detectar_csv(EJEMPLOS / "iris.csv") == {"sep": ",", "encoding": "utf-8-sig"}
    opciones = detectar_csv(EJEMPLOS / "iris_excel_colombia.csv")
    assert opciones == {"sep": ";", "encoding": "latin-1", "decimal": ","}
    filas = leer_muestra(EJEMPLOS / "iris_excel_colombia.csv", "csv", opciones)
    assert filas[0]["Largo del sépalo (cm)"] == 5.1 and len(filas) == 150


def test_lee_excel():
    filas = leer_muestra(EJEMPLOS / "iris.xlsx", "xlsx", {})
    assert len(filas) == 150 and filas[0]["Especie"] == "setosa"


@pytest.fixture
def pendiente_archivo():
    return {"nombre": "iris", "titulo": "Iris", "descripcion": "", "etiquetas": ["flores"], "tipo": "file",
            "archivo": "iris.csv", "formato": "csv", "opciones": {"sep": ","}}


def test_yaml_de_archivo_con_llave_y_obligatorias(pendiente_archivo):
    d = _yaml_fuente(pendiente_archivo, {"llave": "id", "obligatorias": ["species", "id"]})
    spec = SourceSpec.model_validate(d)
    assert spec.title == "Iris" and spec.description == "Iris" and spec.primary_key == ["id"]
    assert spec.contract.required_columns == ["id", "species"]
    assert [(c.column, c.rule, c.severity) for c in spec.contract.checks] == [
        ("id", "not_null", "error"), ("id", "unique", "warn"), ("species", "not_null", "warn")]
    assert d["connection"]["path"].endswith("data/landing/iris.csv")


def test_yaml_de_api_nunca_guarda_el_secreto():
    p = {"nombre": "api", "titulo": "API", "descripcion": "d", "etiquetas": [], "tipo": "rest",
         "url": "https://x.org/r.json", "ruta_registros": "data.items", "paginacion": "offset", "tam_pagina": 100,
         "param_limite": "$limit", "param_desplazamiento": "$offset", "param_pagina": "page", "max_registros": 500,
         "auth_header": "X-App-Token", "auth_variable": "MI_TOKEN"}
    d = _yaml_fuente(p, {"cursor": "fecha", "valor_inicial": "2026-01-01"})
    assert d["connection"]["auth"]["value"] == "${MI_TOKEN:-}"
    spec = SourceSpec.model_validate(d)
    assert spec.pagination.limit_param == "$limit" and spec.max_records == 500
    assert spec.incremental.cursor_field == "fecha" and spec.connection.records_path == "data.items"
