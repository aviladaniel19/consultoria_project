"""Motor de calidad MinTIC: un caso por cada error frecuente, puntaje, nivel y comparativo."""
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from plataforma.quality.mintic import MetadatosDCAT, MinTicQualityEngine

MOTOR = MinTicQualityEngine()
COMPLETOS = MetadatosDCAT(
    titulo="Sedes educativas oficiales por municipio",
    descripcion="Listado de las sedes educativas oficiales del país, con su municipio, zona y número de "
                "estudiantes matriculados. Fuente: sistema de matrícula.",
    entidad="Ministerio de Educación Nacional", correo="datos@mineducacion.gov.co",
    usuario_publicador="Ministerio de Educación Nacional", categoria="Educación", frecuencia="Anual",
    cobertura="Nacional", licencia="CC BY-SA 4.0",
)


def limpio(n: int = 60) -> pd.DataFrame:
    return pd.DataFrame({
        "codigo_sede": [f"S{i:04d}" for i in range(n)],
        "municipio": [("Tunja", "Duitama", "Sogamoso")[i % 3] for i in range(n)],
        "zona": [("urbana", "rural")[i % 2] for i in range(n)],
        "estudiantes": [100 + 7 * i for i in range(n)],
        "fecha_corte": ["2026-03-31"] * (n - 1) + ["2026-06-30"],
    })


def metadatos(df: pd.DataFrame, **cambios) -> MetadatosDCAT:
    descripciones = {c: f"Descripción completa de la columna {c}" for c in df.columns}
    return COMPLETOS.model_copy(update={"descripciones_columnas": descripciones, "llave": ["codigo_sede"]} | cambios)


def codigos(df: pd.DataFrame, m: MetadatosDCAT | None = None) -> dict[str, list]:
    reporte = MOTOR.evaluar(df, m or metadatos(df))
    out: dict[str, list] = {}
    for h in reporte.hallazgos_errores:
        out.setdefault(h.codigo, []).append(h)
    return out


def test_conjunto_limpio_es_excelente():
    df = limpio()
    r = MOTOR.evaluar(df, metadatos(df))
    assert r.hallazgos_errores == [] and r.score_global == 100 and r.nivel_cumplimiento == "Excelente"
    assert {c.criterio for c in r.criterios_evaluados} >= {"Completitud", "Unicidad", "Confidencialidad"}
    assert "ERR006" in r.revision_manual and "plataforma" in r.nota_metodologica


@pytest.mark.parametrize("titulo,fragmento", [
    ("Matrícula 2024", "vigencia"),
    ("Reporte SIMAT de sedes", "siglas"),
    ("Sedes_educativas@oficiales", "caracteres especiales"),
    ("Sedes", "demasiado corto"),
])
def test_err001_titulo_mal_nombrado(titulo, fragmento):
    df = limpio()
    h = codigos(df, metadatos(df, titulo=titulo))["ERR001"]
    assert fragmento in h[0].mensaje and h[0].ubicacion == "metadatos: título" and h[0].criterio == "Comprensibilidad"


def test_err001_descripcion_vacia_y_err017_descripcion_corta():
    df = limpio()
    assert codigos(df, metadatos(df, descripcion=""))["ERR001"][0].ubicacion == "metadatos: descripción"
    assert "ERR017" in codigos(df, metadatos(df, descripcion="Sedes del país."))


def test_err002_metadatos_incompletos_y_err003_publicador_personal():
    df = limpio()
    c = codigos(df, metadatos(df, entidad=None, correo="", licencia=None, categoria="Otros"))
    assert "entidad productora, correo de contacto, licencia" in c["ERR002"][0].mensaje
    assert any("Otros" in h.mensaje for h in c["ERR002"])
    c = codigos(df, metadatos(df, usuario_publicador="Juan Pérez", correo="juan@gmail.com"))
    assert len(c["ERR003"]) == 2


def test_err004_sin_filas_y_err008_una_columna_bloquean():
    vacio = limpio().iloc[0:0]
    r = MOTOR.evaluar(vacio, metadatos(vacio))
    assert r.nivel_cumplimiento == "No Aprobado" and any(h.codigo == "ERR004" and h.bloqueante
                                                         for h in r.hallazgos_errores)
    una = limpio()[["municipio"]]
    assert MOTOR.evaluar(una, metadatos(una)).nivel_cumplimiento == "No Aprobado"


def test_err005_pocas_filas_y_err008_1_pocas_columnas():
    df = limpio(20)[["codigo_sede", "municipio", "estudiantes"]]
    c = codigos(df)
    assert c["ERR005"][0].afectados == 20 and c["ERR005"][0].severidad == "advertencia"
    assert c["ERR008_1"][0].afectados == 3


def test_err007_vacios_y_rellenos_no_estandarizados():
    df = limpio()
    df.loc[0:5, "zona"] = None
    df.loc[6:8, "zona"] = ["N/A", "-", "sin dato"]
    df.loc[9, "zona"] = "   "
    h = codigos(df)["ERR007"][0]
    assert h.columna == "zona" and h.afectados == 10 and h.tasa == pytest.approx(10 / 60, abs=1e-5)
    assert "No aplica" in h.mensaje
    assert MOTOR.evaluar(df, metadatos(df)).score_global < 100


def test_err008_2_columnas_sin_nombre_y_err008_3_sin_descripcion():
    df = limpio().rename(columns={"zona": "Unnamed: 3"})
    c = codigos(df, metadatos(df).model_copy(update={"descripciones_columnas": {"municipio": "corta"}}))
    assert c["ERR008_2"][0].columna == "Unnamed: 3"
    assert c["ERR008_3"][0].afectados == 5


def test_err009_direccion_sin_coordenadas_y_rango_de_colombia():
    df = limpio()
    df["direccion_sede"] = ["Calle 10 # 5-20"] * len(df)
    assert codigos(df)["ERR009"][0].columna == "direccion_sede"
    df["latitud"] = ["5,54"] * 58 + ["48,85", "-75,58"]         # coma decimal; París; intercambiada
    df["longitud"] = [-73.36] * 59 + [200.0]
    c = codigos(df)
    assert "ERR009" not in c
    rango = {h.columna: h for h in c["PD-GEO-RANGO"]}
    assert rango["latitud"].afectados == 2 and rango["longitud"].afectados == 1


def test_err018_datos_personales_sin_revelar_valores():
    df = limpio()
    df["numero_de_identificacion"] = [1_020_000_000 + i for i in range(len(df))]
    df["correo"] = [f"persona{i}@gmail.com" for i in range(len(df))]
    df["celular"] = [f"3{100000000 + i}" for i in range(len(df))]
    df["domicilio"] = [f"Cra 7 # {i}-15" for i in range(len(df))]
    df["nit_proveedor"] = [900_000_000 + i for i in range(len(df))]          # un NIT no es dato personal
    reporte = MOTOR.evaluar(df, metadatos(df))
    pii = {h.columna: h for h in reporte.hallazgos_errores if h.codigo == "ERR018"}
    assert set(pii) == {"numero_de_identificacion", "correo", "celular", "domicilio"}
    assert "personales" in pii["correo"].mensaje and all(h.severidad == "error" for h in pii.values())
    volcado = reporte.model_dump_json()
    assert "1020000000" not in volcado and "persona0@gmail.com" not in volcado
    assert next(c for c in reporte.criterios_evaluados if c.criterio == "Confidencialidad").puntaje == 0


def test_err019_tipos_formatos_y_datos_ficticios():
    df = limpio().astype({"estudiantes": object})
    df.loc[0:2, "estudiantes"] = ["doce", "muchos", "N/A"]          # N/A es un relleno, no un error de tipo
    df["fecha_visita"] = ["31/12/2025"] * len(df)
    df["rector"] = ["XXXXX", "test"] + ["Ana"] * (len(df) - 2)
    df["area"] = ["1.250,50"] * len(df)
    mensajes = {h.columna: h.mensaje for h in codigos(df)["ERR019"]}
    assert "2 valores no son números" in mensajes["estudiantes"]
    assert "ISO 8601" in mensajes["fecha_visita"] and "ficticios" in mensajes["rector"]
    assert "coma decimal" in mensajes["area"]


def test_err020_filas_e_identificadores_duplicados():
    df = limpio()
    df = pd.concat([df, df.iloc[:3]], ignore_index=True)             # 3 copias exactas
    df.loc[len(df)] = ["S0010", "Paipa", "rural", 1, "2026-03-31"]   # mismo id, datos distintos
    h = {x.columna: x.afectados for x in codigos(df)["ERR020"]}
    assert h == {None: 3, "codigo_sede": 1}


def test_columnas_redundantes_constantes_totales_y_vigencias():
    df = limpio()
    df["municipio_nombre"] = df["municipio"]
    df["pais"] = "Colombia"
    df.loc[len(df)] = ["S9999", "TOTAL", "urbana", 99999, "2026-03-31", "TOTAL", "Colombia"]
    c = codigos(df)
    assert c["PD-COL-REDUNDANTE"][0].columna == "municipio_nombre" and c["PD-COL-CONSTANTE"][0].columna == "pais"
    assert c["ERR016"][0].afectados == 1
    sin_fecha = limpio().drop(columns="fecha_corte")
    assert "ERR011" in codigos(sin_fecha, metadatos(sin_fecha, titulo="Sedes educativas oficiales 2024"))


def test_err014_desactualizado_segun_la_frecuencia():
    df = limpio()
    viejo = datetime.now(UTC) - timedelta(days=200)
    assert "ERR014" in codigos(df, metadatos(df, frecuencia="Mensual", ultima_actualizacion=viejo))
    assert "ERR014" not in codigos(df, metadatos(df, frecuencia="Anual", ultima_actualizacion=viejo))


def test_comparativo_mide_el_impacto_de_la_limpieza():
    sucio = limpio().rename(columns={"zona": "Zona Sede"})
    sucio.loc[0:9, "Zona Sede"] = "N/A"
    sucio = pd.concat([sucio, sucio.iloc[:6]], ignore_index=True)
    m = metadatos(sucio)

    def limpiar(df: pd.DataFrame) -> pd.DataFrame:
        df = df.drop_duplicates().rename(columns={"Zona Sede": "zona_sede"})
        return df.assign(zona_sede=df["zona_sede"].replace("N/A", None))

    equivalencias = {"Zona Sede": "zona_sede"}
    m_despues = m.renombrar(equivalencias)
    antes = MOTOR.evaluar(sucio, m, "antes")
    despues = MOTOR.evaluar(limpiar(sucio), m_despues, "despues")
    comp = MOTOR.comparar(antes, despues, equivalencias)
    assert comp.filas_antes == 66 and comp.filas_despues == 60
    assert comp.score_despues > comp.score_antes and comp.cambio_score == pytest.approx(
        comp.score_despues - comp.score_antes)
    assert [h.codigo for h in comp.resueltos] == ["ERR020"]                 # los duplicados desaparecen
    assert [(h.codigo, h.columna) for h in comp.persistentes] == [("ERR007", "zona_sede")]   # N/A -> vacío
    assert comp.nuevos == []
    unicidad = next(c for c in comp.criterios if c.criterio == "Unicidad")
    assert unicidad.antes < 10 and unicidad.despues == 10 and unicidad.cambio > 0

    a, d, c2 = MOTOR.ejecutar(sucio, m, limpiar, equivalencias)             # el mismo flujo en una llamada
    assert (a.score_global, d.filas) == (antes.score_global, 60) and c2.cambio_score > 0


def test_una_regla_que_falla_no_tumba_la_evaluacion():
    def rota(df, m):
        raise RuntimeError("boom")
    df = limpio()
    assert MinTicQualityEngine(reglas=[rota]).evaluar(df, metadatos(df)).score_global == 100
