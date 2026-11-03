import httpx
import respx

from plataforma.ingestion.engine import diff_schema, extract, is_after, max_cursor, next_cursor
from plataforma.ingestion.rest import retry_wait
from plataforma.registry.models import SourceSpec
from plataforma.storage.catalog import redacted_spec

URL = "https://api.ejemplo.com/items"


def spec(**over):
    base = {
        "name": "items",
        "description": "x",
        "type": "rest",
        "connection": {"base_url": URL, "params": {"$where": "activo = true"}, "max_retries": 2},
        "pagination": {"type": "offset", "limit_param": "$limit", "offset_param": "$offset", "page_size": 2},
        "incremental": {"cursor_field": "fecha", "initial_value": "2026-01-01",
                        "filter": {"param": "$where", "template": "{field} > '{value}'"}},
    }
    base.update(over)
    return SourceSpec.model_validate(base)


DATA = [{"id": i, "fecha": f"2026-02-0{i}T00:00:00.000"} for i in range(1, 6)]


def paginar(request: httpx.Request) -> httpx.Response:
    off, lim = int(request.url.params["$offset"]), int(request.url.params["$limit"])
    return httpx.Response(200, json=DATA[off : off + lim])


@respx.mock
def test_offset_recorre_todas_las_paginas_y_combina_filtros():
    route = respx.get(URL).mock(side_effect=paginar)
    recs, extraidos = extract(spec(), "2026-01-01", httpx.Client())
    assert [r["id"] for r in recs] == [1, 2, 3, 4, 5]
    assert extraidos == 5 and route.call_count == 3
    where = route.calls[0].request.url.params["$where"]
    assert where == "(activo = true) AND (fecha > '2026-01-01')"


@respx.mock
def test_respeta_max_records():
    respx.get(URL).mock(side_effect=paginar)
    recs, _ = extract(spec(max_records=3), None, httpx.Client())
    assert len(recs) == 3


@respx.mock
def test_filtra_en_python_lo_ya_cargado():
    respx.get(URL).mock(side_effect=paginar)
    recs, extraidos = extract(spec(), "2026-02-03T00:00:00", httpx.Client())
    assert [r["id"] for r in recs] == [4, 5] and extraidos == 5


@respx.mock
def test_reintenta_ante_429(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json=DATA[:1])])
    recs, _ = extract(spec(pagination={"type": "none"}), None, httpx.Client())
    assert len(recs) == 1


@respx.mock
def test_records_path_y_cursor():
    s = spec(connection={"base_url": URL, "records_path": "data.items"},
             pagination={"type": "cursor", "cursor_param": "after", "next_cursor_path": "data.next"},
             incremental=None)
    respx.get(URL).mock(side_effect=[
        httpx.Response(200, json={"data": {"items": [{"id": 1}], "next": "c2"}}),
        httpx.Response(200, json={"data": {"items": [{"id": 2}], "next": None}}),
    ])
    recs, _ = extract(s, None, httpx.Client())
    assert [r["id"] for r in recs] == [1, 2]


def test_comparacion_de_cursores():
    assert is_after("2026-02-01T00:00:00.000", "2026-01-31")
    assert not is_after("2026-01-01T00:00:00.000", "2026-01-01")
    assert is_after("10", "9")                      # numérico, no lexicográfico
    assert max_cursor(["9", "10", None, ""]) == "10"


def test_cursor_nulo_no_es_posterior():
    assert not is_after(None, "2026-01-01") and not is_after("", "2026-01-01")
    assert is_after(None, None)                     # sin cursor todo entra


def test_cursor_retrocede_si_el_tope_corta_un_grupo():
    vals = ["2026-01-01", "2026-01-02", "2026-01-02", None]
    assert next_cursor(vals, truncated=False) == "2026-01-02"
    assert next_cursor(vals, truncated=True) == "2026-01-01"     # el 2 de enero pudo quedar a medias
    assert next_cursor(["2026-01-02"] * 3, truncated=True) == "2026-01-02"   # no hay a dónde retroceder


@respx.mock
def test_auth_con_cliente_inyectado():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[]))
    s = spec(connection={"base_url": URL, "auth": {"type": "bearer", "token": "t0k"}},
             pagination={"type": "none"})
    extract(s, None, httpx.Client())
    assert route.calls[0].request.headers["Authorization"] == "Bearer t0k"


def test_retry_after_numero_o_fecha():
    assert retry_wait("3", 1) == 3
    assert retry_wait("Wed, 21 Oct 2015 07:28:00 GMT", 1) == 0    # fecha pasada: sin espera
    assert retry_wait("basura", 1) == 1 and retry_wait(None, 4) == 4


def test_esquema_acumulativo():
    old = {"a": "numeric", "b": "text", "c": "unknown"}
    merged, added, retyped = diff_schema(old, {"a": "unknown", "b": "numeric", "c": "datetime", "d": "text"})
    assert merged == {"a": "numeric", "b": "numeric", "c": "datetime", "d": "text"}
    assert added == ["d"] and retyped == ["b"]


def test_catalogo_oculta_secretos_en_headers_y_params():
    s = spec(connection={"base_url": URL, "headers": {"Authorization": "Bearer x", "Accept-Language": "es"},
                         "params": {"api_key": "k", "$where": "a = 1"}})
    conn = redacted_spec(s)["connection"]
    assert conn["headers"] == {"Authorization": "***", "Accept-Language": "es"}
    assert conn["params"] == {"api_key": "***", "$where": "a = 1"}
