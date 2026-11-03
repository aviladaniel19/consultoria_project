from datetime import UTC, datetime, timedelta

import pytest

from plataforma.consultas import ConsultaInvalida, Filtro, _armar
from plataforma.web.datos import normalizar, titulo_y_descripcion
from plataforma.web.rutas import _destino_seguro, fmt_compacto, fmt_fecha, fmt_hace, fmt_num, fmt_pct

COLS = [{"name": "precio", "type": "numeric"}, {"name": "depto", "type": "text"},
        {"name": "fecha", "type": "date"}, {"name": "datos", "type": "jsonb"}]


def test_filtro_desde_texto():
    assert Filtro.desde_texto("depto:eq:Bogotá") == Filtro("depto", "eq", "Bogotá")
    assert Filtro.desde_texto("hora:eq:10:30").valor == "10:30"      # el valor puede tener ':'
    assert Filtro.desde_texto("precio:vacio") == Filtro("precio", "vacio", "")
    with pytest.raises(ConsultaInvalida):
        Filtro.desde_texto("sin_operador")


def test_armar_valida_y_parametriza():
    where, order, params = _armar(COLS, [Filtro("precio", "ge", "100"), Filtro("depto", "contiene", "50%_")],
                                  "-precio")
    assert where == (' WHERE "precio" >= CAST(:f0 AS numeric)'
                     " AND CAST(\"depto\" AS text) ILIKE :f1 ESCAPE '\\'")
    assert params == {"f0": "100", "f1": "%50\\%\\_%"}          # comodines del usuario escapados
    assert order == ' ORDER BY "precio" DESC NULLS LAST'
    assert _armar(COLS, [Filtro("fecha", "vacio")], None)[0] == ' WHERE "fecha" IS NULL'
    # tipos sin conversión segura se comparan tal cual
    assert "CAST" not in _armar(COLS, [Filtro("datos", "eq", "{}")], None)[0]


@pytest.mark.parametrize("filtros,orden", [
    ([Filtro("no_existe", "eq", "1")], None),
    ([Filtro("precio", "drop table", "1")], None),
    ([], 'precio"; DROP TABLE x; --'),
])
def test_armar_rechaza_columnas_y_operadores_desconocidos(filtros, orden):
    with pytest.raises(ConsultaInvalida):
        _armar(COLS, filtros, orden)


def test_formatos_de_colombia():
    assert fmt_num(1250000) == "1.250.000" and fmt_num(1234.5, 2) == "1.234,50"
    assert fmt_num(None) == "—"
    assert fmt_compacto(1_250_000_000) == "1.250 M" and fmt_compacto(48_500_000) == "48,5 M"
    assert fmt_compacto(950) == "950"
    assert fmt_pct(0.0016, 2) == "0,16 %"
    # 05:15 UTC son las 00:15 en Colombia (UTC-5)
    assert fmt_fecha(datetime(2026, 11, 3, 5, 15, tzinfo=UTC)) == "03 nov 2026, 00:15"
    assert fmt_hace(datetime.now(UTC) - timedelta(hours=2, minutes=5)) == "hace 2 horas"
    assert fmt_hace(datetime.now(UTC) - timedelta(days=1)) == "hace 1 día"
    assert fmt_hace(None) == "nunca"


def test_titulos_y_busqueda_sin_tildes():
    assert titulo_y_descripcion("Contratación mensual\nNúmero de procesos.", "x") == (
        "Contratación mensual", "Número de procesos.")
    assert titulo_y_descripcion(None, "salud_fuentes") == ("Salud fuentes", "")
    assert normalizar("Contratación PÚBLICA") == "contratacion publica"


@pytest.mark.parametrize("destino,esperado", [
    ("/datos/analitico/x?p=2", "/datos/analitico/x?p=2"),
    ("https://otro-sitio.com", "/"), ("//otro-sitio.com", "/"), (None, "/"),
])
def test_ingreso_solo_redirige_a_rutas_locales(destino, esperado):
    assert _destino_seguro(destino) == esperado
