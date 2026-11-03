"""Prueba de punta a punta contra PostgreSQL real con una API simulada.

    PLATAFORMA_TEST_DATABASE_URL=postgresql+psycopg://... pytest tests/test_integracion.py
"""
import json
import os

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from typer.testing import CliRunner

from plataforma.api.main import app, db
from plataforma.cli import app as cli_app
from plataforma.config import get_settings
from plataforma.ingestion.engine import run_source
from plataforma.registry.models import SourceSpec
from plataforma.storage.db import bootstrap, get_engine

URL_DB = os.environ.get("PLATAFORMA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL_DB, reason="define PLATAFORMA_TEST_DATABASE_URL")
API = "https://api.ejemplo.com/procesos"

SPEC = SourceSpec.model_validate({
    "name": "procesos_demo",
    "description": "fuente simulada",
    "tags": ["demo"],
    "type": "rest",
    "connection": {"base_url": API, "auth": {"type": "bearer", "token": "secreto-123"}},
    "pagination": {"type": "offset", "limit_param": "$limit", "offset_param": "$offset", "page_size": 2},
    "incremental": {"cursor_field": "fecha", "initial_value": "2026-01-01",
                    "filter": {"param": "$where", "template": "{field} > '{value}'"}},
    "primary_key": ["id"],
    "contract": {"required_columns": ["id", "fecha"],
                 "checks": [{"column": "id", "rule": "not_null", "severity": "error"},
                            {"column": "precio", "rule": "non_negative"}]},
})


def servir(datos):
    def handler(request: httpx.Request) -> httpx.Response:
        corte = request.url.params["$where"].split("'")[1]
        nuevos = [d for d in datos if d["fecha"] > corte]
        off, lim = int(request.url.params["$offset"]), int(request.url.params["$limit"])
        return httpx.Response(200, json=nuevos[off : off + lim])
    return handler


@pytest.fixture(autouse=True)
def api_abierta(monkeypatch):
    # que las claves de un .env local no cambien el resultado de las pruebas
    monkeypatch.setattr(get_settings(), "api_keys", "")


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL_DB)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS origen, estandarizado, analitico, meta CASCADE"))
    bootstrap(eng)
    yield eng
    eng.dispose()


@respx.mock
def test_ciclo_completo(engine):
    lote1 = [
        {"id": "1", "fecha": "2026-02-01T00:00:00.000", "precio": "100"},
        {"id": "2", "fecha": "2026-02-02T00:00:00.000", "precio": "-3"},
        {"id": "3", "fecha": "2026-02-03T00:00:00.000", "precio": "50"},
    ]
    respx.get(API).mock(side_effect=servir(lote1))
    r1 = run_source(engine, SPEC, client=httpx.Client())
    assert r1.status == "success_with_warnings"          # precio negativo es solo advertencia
    assert (r1.loaded, r1.schema_version) == (3, 1)
    assert r1.cursor_after == "2026-02-03T00:00:00.000"

    # segunda carga: solo lo nuevo, aparece una columna y un id nulo (regla de severidad error)
    lote2 = lote1 + [
        {"id": "4", "fecha": "2026-02-04T00:00:00.000", "precio": "10", "entidad": "MinTIC"},
        {"id": None, "fecha": "2026-02-05T00:00:00.000", "precio": "20", "entidad": "DANE"},
    ]
    respx.get(API).mock(side_effect=servir(lote2))
    r2 = run_source(engine, SPEC, client=httpx.Client())
    assert r2.status == "failed_quality" and r2.loaded == 2
    assert r2.schema_version == 2 and r2.schema_changes["added"] == ["entidad"]
    assert r2.cursor_after == "2026-02-05T00:00:00.000"

    # tercera carga: nada nuevo
    r3 = run_source(engine, SPEC, client=httpx.Client())
    assert (r3.status, r3.loaded) == ("success", 0)

    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM origen.procesos_demo")).scalar() == 5
        spec_guardado = c.execute(text("SELECT spec FROM meta.sources WHERE name='procesos_demo'")).scalar()
        assert spec_guardado["connection"]["auth"]["token"] == "***"      # sin secretos en el catálogo
        perfiles = c.execute(text("SELECT count(*) FROM meta.column_profiles")).scalar()
        assert perfiles == 3 + 4

    # una API que falla queda registrada sin dejar filas
    respx.get(API).mock(return_value=httpx.Response(404, text="no existe"))
    r4 = run_source(engine, SPEC, client=httpx.Client())
    assert r4.status == "failed" and "404" in r4.error

    # la API de servicio descubre la fuente sola
    def override():
        with engine.connect() as conn:
            yield conn
    app.dependency_overrides[db] = override
    with engine.begin() as c:
        c.execute(text("CREATE TABLE analitico.demo AS SELECT 1 AS x UNION SELECT 2"))
    cli = TestClient(app)
    fuentes = cli.get("/sources").json()
    assert fuentes[0]["name"] == "procesos_demo" and fuentes[0]["last_status"] == "failed"
    assert cli.get("/sources", params={"tag": "otro"}).json() == []
    detalle = cli.get("/sources/procesos_demo").json()
    assert "entidad" in detalle["schema"]["columns"]
    assert len(cli.get("/sources/procesos_demo/runs").json()) == 4
    assert len(cli.get("/sources/procesos_demo/profile-history/precio").json()) == 2
    assert cli.get(f"/runs/{r2.run_id}/quality").json()[0]["passed"] is False
    assert cli.get("/datasets").json()[0]["name"] == "demo"
    ds = cli.get("/datasets/analitico/demo", params={"order_by": "-x"}).json()
    assert ds["total"] == 2 and ds["data"][0]["x"] == 2
    assert cli.get("/datasets/analitico/demo", params={"order_by": "x; drop table x"}).status_code == 400
    assert cli.get("/datasets/analitico/no_existe").status_code == 404
    app.dependency_overrides.clear()


def test_clave_api_lector_y_mcp(engine, monkeypatch):
    """Usa los datos que dejó test_ciclo_completo (procesos_demo y analitico.demo)."""
    settings = get_settings()

    # API con claves: /health sigue público, el resto exige X-API-Key
    def override():
        with engine.connect() as conn:
            yield conn
    app.dependency_overrides[db] = override
    monkeypatch.setattr(settings, "api_keys", "k-docentes")
    cli = TestClient(app)
    assert cli.get("/health").status_code == 200
    assert cli.get("/sources").status_code == 401
    assert cli.get("/sources", headers={"X-API-Key": "mala"}).status_code == 401
    assert cli.get("/sources", headers={"X-API-Key": "k-docentes"}).status_code == 200
    app.dependency_overrides.clear()

    # usuario de solo lectura: ve analitico y meta, no puede escribir ni ver la capa de origen
    monkeypatch.setattr(settings, "database_url", URL_DB)
    get_engine.cache_clear()
    r = CliRunner().invoke(cli_app, ["crear-lector", "lector_prueba", "--clave", "clave:con%raros'"])
    assert r.exit_code == 0, r.output
    url_lector = make_url(URL_DB).set(username="lector_prueba", password="clave:con%raros'")
    lector = create_engine(url_lector)
    with lector.connect() as c:
        assert c.execute(text("SELECT sum(x) FROM analitico.demo")).scalar() == 3
        assert c.execute(text("SELECT count(*) FROM meta.runs")).scalar() == 4
        with pytest.raises(Exception, match="permission denied"):
            c.execute(text("SELECT 1 FROM origen.procesos_demo"))
    with lector.connect() as c, pytest.raises(Exception, match="permission denied"):
        c.execute(text("INSERT INTO analitico.demo VALUES (9)"))
    lector.dispose()

    # herramientas MCP conectadas como el lector
    pytest.importorskip("mcp")
    from plataforma import mcp_server

    monkeypatch.setattr(settings, "mcp_database_url", url_lector.render_as_string(hide_password=False))
    assert json.loads(mcp_server.listar_fuentes())[0]["name"] == "procesos_demo"
    assert json.loads(mcp_server.listar_datasets("analitico"))[0]["name"] == "demo"
    assert json.loads(mcp_server.describir_dataset("analitico", "demo"))["columnas"][0]["name"] == "x"
    assert json.loads(mcp_server.consultar_dataset("analitico", "demo", ordenar_por="-x"))["data"][0]["x"] == 2
    res = json.loads(mcp_server.consulta_sql("SELECT sum(x)::int AS s FROM demo WHERE 'a%' LIKE 'a%'"))
    assert res == {"columnas": ["s"], "filas": [{"s": 3}], "truncado": False}
    assert "error" in json.loads(mcp_server.consulta_sql("SELECT * FROM no_existe"))
    assert "error" in json.loads(mcp_server.consulta_sql("WITH b AS (DELETE FROM demo RETURNING *) SELECT * FROM b"))
    assert "error" in json.loads(mcp_server.listar_datasets("origen"))
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM analitico.demo")).scalar() == 2   # nada se borró
    get_engine.cache_clear()


def test_frontend_y_filtros(engine, monkeypatch):
    """Recorre el frontend y los filtros de la API con los datos de las pruebas anteriores."""
    from plataforma.web import rutas

    def override():
        with engine.connect() as conn:
            yield conn
    app.dependency_overrides[db] = override
    app.dependency_overrides[rutas.conexion] = override
    with engine.begin() as c:
        c.execute(text("INSERT INTO analitico.demo VALUES (NULL), (30)"))
        c.execute(text("COMMENT ON TABLE analitico.demo IS 'Tabla de demostración\nValores de prueba.'"))
    cli = TestClient(app)
    hx = {"HX-Request": "true"}

    # catálogo, buscador y filtro por texto sin tildes
    pagina = cli.get("/").text
    assert "Tabla de demostración" in pagina and "<b>4</b> filas" in pagina
    assert "Tabla de demostración" in cli.get("/", params={"q": "demostracion"}, headers=hx).text
    assert "No encontramos" in cli.get("/", params={"q": "zzz"}, headers=hx).text
    assert "/datos/analitico/demo" in cli.get("/buscar", params={"q": "demo"}).text

    # ficha y pestañas; sin fuente vinculada no hay pestaña de calidad
    ficha = cli.get("/datos/analitico/demo")
    assert ficha.status_code == 200 and "Valores de prueba." in ficha.text and 'data-pestana="calidad"' not in ficha.text
    columnas = cli.get("/datos/analitico/demo/columnas", headers=hx).text
    assert "Mediana" in columnas and "<svg" in columnas and "25,0 %" in columnas    # 1 vacío de 4
    assert "analitico.demo" in cli.get("/datos/analitico/demo/uso", headers=hx).text
    assert cli.get("/datos/analitico/demo/calidad", headers=hx).status_code == 404
    assert cli.get("/datos/analitico/no_existe").status_code == 404

    # explorador: filtro, orden, valor inválido y descarga
    r = cli.get("/explorar/analitico/demo", params={"fc": "x", "fo": "ge", "fv": "2", "orden": "-x"}, headers=hx)
    assert "2</b> filas coinciden" in r.text
    assert r.text.index('<td class="n">30</td>') < r.text.index('<td class="n">2</td>')   # orden descendente
    r = cli.get("/explorar/analitico/demo", params={"fc": "x", "fo": "gt", "fv": "abc"})
    assert r.status_code == 200 and "valor de filtro no válido" in r.text
    csv_excel = cli.get("/explorar/analitico/demo/csv", params={"fc": "x", "fo": "no_vacio", "fv": "", "sep": ";"})
    assert csv_excel.text.splitlines() == ["﻿x", "1", "2", "30"]
    assert "salud" in cli.get("/salud").text.lower() and "procesos_demo" in cli.get("/salud").text

    # filtros y CSV en la API
    d = cli.get("/datasets/analitico/demo", params={"filtro": ["x:ge:2"], "order_by": "-x"}).json()
    assert d["total"] == 2 and d["data"][0]["x"] == 30 and d["filters"] == ["x:ge:2"]
    assert cli.get("/datasets/analitico/demo", params={"filtro": "x:ge:abc"}).status_code == 400
    assert cli.get("/datasets/analitico/demo", params={"filtro": "y:eq:1"}).status_code == 400
    assert cli.get("/datasets/analitico/demo/csv").text.splitlines()[0] == "﻿x"

    # con claves configuradas, el frontend pide ingresar una vez y recuerda la sesión
    monkeypatch.setattr(get_settings(), "api_keys", "k-front")
    anonimo = TestClient(app)
    r = anonimo.get("/explorar", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ingresar?siguiente=%2Fexplorar"
    assert anonimo.get("/buscar", params={"q": "x"}, headers=hx).headers["HX-Redirect"].startswith("/ingresar")
    r = anonimo.post("/ingresar", data={"clave": "mala", "siguiente": "/explorar"}, follow_redirects=False)
    assert "error=1" in r.headers["location"]
    r = anonimo.post("/ingresar", data={"clave": "k-front", "siguiente": "https://otro.com"}, follow_redirects=False)
    assert r.headers["location"] == "/" and "httponly" in r.headers["set-cookie"].lower()
    assert anonimo.get("/explorar").status_code == 200
    assert anonimo.get("/static/css/app.css").status_code == 200
    app.dependency_overrides.clear()
    with engine.begin() as c:
        c.execute(text("DELETE FROM analitico.demo WHERE x IS NULL OR x = 30"))


def test_migra_esquemas_con_nombres_antiguos(engine):
    """Una base creada cuando las capas se llamaban bronze/silver/gold se renombra sin perder datos."""
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS origen, estandarizado, analitico CASCADE"))
        c.execute(text("CREATE SCHEMA bronze; CREATE SCHEMA silver; CREATE SCHEMA gold"))
        c.execute(text("CREATE TABLE bronze.vieja AS SELECT 1 AS x"))
    bootstrap(engine)
    bootstrap(engine)                                   # idempotente: la segunda vez no hace nada
    with engine.connect() as c:
        esquemas = set(c.execute(text("SELECT nspname FROM pg_namespace")).scalars())
        assert {"origen", "estandarizado", "analitico"} <= esquemas
        assert not {"bronze", "silver", "gold"} & esquemas
        assert c.execute(text("SELECT x FROM origen.vieja")).scalar() == 1
