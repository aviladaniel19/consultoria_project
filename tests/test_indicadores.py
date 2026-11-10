from plataforma.indicadores import Columna, sugerir, temas_de

CREDITO = [
    Columna("numero_de_identificacion", "numero"),
    Columna("caso_no", "texto", 5000),
    Columna("etapa", "texto", 6),
    Columna("departamento", "texto", 30),
    Columna("ciudad", "texto", 400),
    Columna("fecha_creacion_proceso", "fecha"),
    Columna("fecha_aprobacion", "fecha"),
    Columna("actividad_vence_en", "numero"),
    Columna("valor_credito", "numero"),
]


def nombres(sugerencias) -> list[str]:
    return [s.nombre for s in sugerencias]


def test_dataset_de_credito_recibe_indicadores_del_tema():
    s = sugerir("estandarizado.base_credito", CREDITO, "Base crédito hipotecario",
                "Casos en proceso de aprobación", ["banca"], excluir=["numero_de_identificacion"])
    n = nombres(s)
    assert n[0] == "Embudo por etapa" and s[0].grupo == "Tema: Crédito y finanzas"     # lo temático va primero
    assert {"Casos vencidos o por vencer", "Monto promedio y total (valor_credito)", "Total de registros",
            "Registros por mes (fecha_creacion_proceso)", "Días entre fecha_creacion_proceso y fecha_aprobacion",
            "Cobertura y ranking por departamento"} <= set(n)
    assert all("estandarizado.base_credito" in x.sql for x in s) and len(n) == len(set(n))
    # la cédula está excluida por ser dato personal: no se agrupa ni se promedia por ella
    assert not any("numero_de_identificacion" in x.columnas for x in s if x.grupo != "General")
    assert "ciudad" not in " ".join(n)          # 400 valores distintos: demasiados para una distribución


def test_dataset_generico_solo_usa_el_esquema():
    cols = [Columna("especie", "texto", 3), Columna("largo_del_petalo_cm", "numero"), Columna("activo", "booleano", 2)]
    s = sugerir("estandarizado.flores", cols, "Flores", "Medidas de flores")
    assert temas_de("Flores", "Medidas de flores", [], cols) == []
    assert not any(x.grupo.startswith("Tema") for x in s)
    assert {"Total de registros", "Distribución por especie", "Promedio de largo_del_petalo_cm por especie"} \
        <= set(nombres(s))
    sql = next(x.sql for x in s if x.nombre == "Distribución por especie")
    assert sql.startswith('SELECT "especie", count(*)') and "\n" not in sql


def test_el_tema_se_reconoce_por_columnas_y_no_inventa_indicadores_sin_datos():
    cols = [Columna("contratista", "texto", 900), Columna("modalidad", "texto", 5), Columna("valor", "numero")]
    assert temas_de("Procesos", "", [], cols) == ["Contratación pública"]
    n = nombres(sugerir("analitico.procesos", cols, "Procesos"))
    assert "Valor total contratado (valor)" in n and "Concentración por contratista" in n
    assert not any(x.startswith("Registros por mes") for x in n)        # no hay columna de fecha
    assert sugerir("estandarizado.x", [Columna("a", "otro")])[0].nombre == "Total de registros"
