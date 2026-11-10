"""Sugerencias de indicadores (KPI) para un dataset, a partir de su esquema y de su tema.

Son reglas deterministas: leen los tipos, los nombres de las columnas, cuántos valores distintos
tienen y las palabras del título, la descripción y las etiquetas. No usan los datos fila a fila
ni servicios externos. Cada sugerencia trae una consulta SQL lista para ejecutar.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

MAX_CATEGORIAS = 40          # hasta cuántos valores distintos tiene una columna «categórica»
MAX_SUGERENCIAS = 14

IDENTIFICADOR = {"id", "codigo", "cod", "identificacion", "nit", "cedula", "documento", "caso", "consecutivo",
                 "radicado", "numero", "no", "nro", "uid", "llave"}
ESTADO = {"estado", "etapa", "fase", "estatus", "status", "situacion", "resultado", "decision"}
TERRITORIO = {"departamento", "dpto", "depto", "municipio", "mpio", "ciudad", "region", "regional", "localidad",
              "zona", "pais", "territorio", "barrio", "comuna"}
MONTO = {"valor", "monto", "precio", "costo", "saldo", "total", "cuantia", "ingreso", "ingresos", "pago", "cuota",
         "presupuesto", "desembolso", "avaluo", "salario", "tarifa"}
VENCIMIENTO = {"vence", "vencimiento", "limite", "plazo"}

# Tema -> palabras que lo delatan en el título, la descripción, las etiquetas o las columnas.
TEMAS: dict[str, set[str]] = {
    "Crédito y finanzas": {"credito", "creditos", "hipotecario", "prestamo", "cartera", "banca", "banco",
                           "finanzas", "financiero", "desembolso", "leasing", "deudor"},
    "Contratación pública": {"contrato", "contratos", "contratacion", "secop", "licitacion", "adjudicacion",
                             "proveedor", "contratista", "modalidad"},
    "Salud": {"salud", "paciente", "pacientes", "eps", "ips", "hospital", "diagnostico", "vacuna", "vacunacion",
              "morbilidad", "mortalidad", "atencion"},
    "Educación": {"educacion", "matricula", "estudiante", "estudiantes", "colegio", "sede", "docente", "docentes",
                  "icfes", "desercion", "graduados", "universidad"},
}


@dataclass(frozen=True)
class Columna:
    nombre: str
    tipo: str                      # numero | fecha | texto | booleano | otro
    distintos: int | None = None   # valores distintos (texto y booleano)


@dataclass(frozen=True)
class Sugerencia:
    nombre: str
    grupo: str                     # General, Tiempo, Distribución, Magnitud, Territorio o «Tema: …»
    porque: str                    # por qué es relevante para este dataset
    formula: str
    sql: str
    columnas: tuple[str, ...] = field(default_factory=tuple)


def _palabras(texto: object) -> set[str]:
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return set(re.findall(r"[a-z]+", s))


def _q(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


def temas_de(titulo: str, descripcion: str, etiquetas: Sequence[str], columnas: Sequence[Columna]) -> list[str]:
    contexto = _palabras(" ".join([titulo, descripcion, *etiquetas]))
    de_columnas = set().union(*(_palabras(c.nombre) for c in columnas)) if columnas else set()
    # el título y las etiquetas pesan más: una sola coincidencia basta; en columnas se piden dos
    return [t for t, claves in TEMAS.items() if contexto & claves or len(de_columnas & claves) >= 2]


def sugerir(tabla: str, columnas: Sequence[Columna], titulo: str = "", descripcion: str = "",
            etiquetas: Sequence[str] = (), filas: int | None = None,
            excluir: Sequence[str] = ()) -> list[Sugerencia]:
    """Indicadores sugeridos para `tabla` (esquema.nombre). `excluir` son columnas con datos
    personales: no se usan para agrupar ni para listar valores."""
    excluidas = set(excluir)
    usables = [c for c in columnas if c.nombre not in excluidas]

    def con(palabras: set[str], cols: Sequence[Columna] = usables) -> list[Columna]:
        return [c for c in cols if _palabras(c.nombre) & palabras]

    fechas = [c for c in usables if c.tipo == "fecha"]
    categoricas = [c for c in usables if c.tipo in ("texto", "booleano") and c.distintos is not None
                   and 2 <= c.distintos <= MAX_CATEGORIAS]
    numericas = [c for c in usables if c.tipo == "numero" and not _palabras(c.nombre) & IDENTIFICADOR]
    montos = con(MONTO, numericas) or numericas
    estados = con(ESTADO, categoricas)
    territorios = con(TERRITORIO, categoricas) or con(TERRITORIO, [c for c in usables if c.tipo == "texto"])
    ids = [c for c in columnas if _palabras(c.nombre) & IDENTIFICADOR and c.tipo in ("texto", "numero")]
    dimension = (estados or territorios or categoricas or [None])[0]
    out: list[Sugerencia] = []

    def agregar(nombre: str, grupo: str, porque: str, formula: str, sql: str, *cols: Columna | None) -> None:
        usadas = tuple(c.nombre for c in cols if c is not None)
        if not any(s.nombre == nombre for s in out):
            out.append(Sugerencia(nombre, grupo, porque, formula, " ".join(sql.split()), usadas))

    # ------------------------------------------------------------- tema del dataset
    temas = temas_de(titulo, descripcion, etiquetas, columnas)
    for tema in temas:
        grupo = f"Tema: {tema}"
        if tema == "Crédito y finanzas":
            if estados:
                e = estados[0]
                agregar(f"Embudo por {e.nombre}", grupo,
                        "Muestra en qué etapa del proceso de crédito se concentran o se frenan los casos.",
                        "casos en cada etapa ÷ total de casos",
                        f"SELECT {_q(e.nombre)}, count(*) AS casos, round(100.0 * count(*) / sum(count(*)) OVER (), 1) "
                        f"AS porcentaje FROM {tabla} GROUP BY 1 ORDER BY casos DESC", e)
            if vence := con(VENCIMIENTO):
                v = vence[0]
                condicion = (f"{_q(v.nombre)} < now()" if v.tipo == "fecha" else f"{_q(v.nombre)} <= 0"
                             if v.tipo == "numero" else f"{_q(v.nombre)} IS NOT NULL")
                agregar("Casos vencidos o por vencer", grupo,
                        "Los trámites de crédito tienen plazos: los vencidos son el riesgo operativo inmediato.",
                        f"casos donde {v.nombre} ya se cumplió ÷ total de casos",
                        f"SELECT count(*) FILTER (WHERE {condicion}) AS vencidos, count(*) AS total, "
                        f"round(100.0 * count(*) FILTER (WHERE {condicion}) / nullif(count(*), 0), 1) AS porcentaje "
                        f"FROM {tabla}", v)
            if montos and con(MONTO, numericas):
                m = montos[0]
                agregar(f"Monto promedio y total ({m.nombre})", grupo,
                        "El tamaño de la cartera en trámite y el valor típico de una solicitud.",
                        f"suma, promedio y mediana de {m.nombre}",
                        f"SELECT sum({_q(m.nombre)}) AS total, round(avg({_q(m.nombre)}), 2) AS promedio, "
                        f"percentile_cont(0.5) WITHIN GROUP (ORDER BY {_q(m.nombre)}) AS mediana FROM {tabla}", m)
        elif tema == "Contratación pública":
            if montos:
                m = montos[0]
                agregar(f"Valor total contratado ({m.nombre})", grupo,
                        "Dimensiona el gasto público que cubre el conjunto.", f"suma de {m.nombre}",
                        f"SELECT sum({_q(m.nombre)}) AS valor_total, count(*) AS procesos FROM {tabla}", m)
            if quien := con({"proveedor", "contratista", "entidad"}, [c for c in usables if c.tipo == "texto"]):
                p = quien[0]
                valor = f"sum({_q(montos[0].nombre)})" if montos else "count(*)"
                agregar(f"Concentración por {p.nombre}", grupo,
                        "Una alta concentración en pocos actores es una señal de alerta en contratación.",
                        "participación de los 10 primeros en el total",
                        f"SELECT {_q(p.nombre)}, {valor} AS total FROM {tabla} GROUP BY 1 ORDER BY total DESC LIMIT 10",
                        p, montos[0] if montos else None)
        elif tema == "Salud" and territorios:
            t = territorios[0]
            agregar(f"Casos por {t.nombre}", grupo, "Permite comparar la carga entre territorios.",
                    "registros por territorio",
                    f"SELECT {_q(t.nombre)}, count(*) AS casos FROM {tabla} GROUP BY 1 ORDER BY casos DESC", t)
        elif tema == "Educación" and numericas:
            n = numericas[0]
            por = f" GROUP BY {_q(dimension.nombre)} ORDER BY total DESC" if dimension else ""
            agregar(f"Total de {n.nombre}" + (f" por {dimension.nombre}" if dimension else ""), grupo,
                    "Mide la cobertura del servicio educativo que describe el conjunto.", f"suma de {n.nombre}",
                    f"SELECT {_q(dimension.nombre) + ', ' if dimension else ''}sum({_q(n.nombre)}) AS total "
                    f"FROM {tabla}{por}", n, dimension)

    # ------------------------------------------------------------------- generales
    agregar("Total de registros", "General", "Es la línea base de cualquier otro indicador.", "número de filas",
            f"SELECT count(*) AS registros FROM {tabla}")
    if ids:
        i = ids[0]
        agregar(f"Registros únicos por {i.nombre}", "General",
                "Dice cuántas entidades distintas hay y si un mismo identificador se repite.",
                f"valores distintos de {i.nombre}",
                f"SELECT count(DISTINCT {_q(i.nombre)}) AS unicos, count(*) AS registros FROM {tabla}", i)

    # ---------------------------------------------------------------------- tiempo
    if fechas:
        f = fechas[0]
        agregar(f"Registros por mes ({f.nombre})", "Tiempo",
                "La tendencia en el tiempo muestra crecimiento, estacionalidad y caídas.", "registros por mes",
                f"SELECT date_trunc('month', {_q(f.nombre)})::date AS mes, count(*) AS registros FROM {tabla} "
                f"WHERE {_q(f.nombre)} IS NOT NULL GROUP BY 1 ORDER BY 1", f)
    if len(fechas) >= 2:
        a, b = fechas[0], fechas[1]
        agregar(f"Días entre {a.nombre} y {b.nombre}", "Tiempo",
                "Mide cuánto tarda el proceso entre dos hitos (tiempo de ciclo).",
                f"promedio y mediana de ({b.nombre} − {a.nombre}) en días",
                f"SELECT round(avg(abs(extract(epoch FROM {_q(b.nombre)} - {_q(a.nombre)})) / 86400)::numeric, 1) "
                f"AS dias_promedio, round((percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(extract(epoch FROM "
                f"{_q(b.nombre)} - {_q(a.nombre)})) / 86400))::numeric, 1) AS dias_mediana FROM {tabla} "
                f"WHERE {_q(a.nombre)} IS NOT NULL AND {_q(b.nombre)} IS NOT NULL", a, b)

    # ---------------------------------------------------------------- distribución
    for c in (estados + [x for x in categoricas if x not in estados and x not in territorios])[:3]:
        agregar(f"Distribución por {c.nombre}", "Distribución",
                f"Con {c.distintos} valores distintos, muestra cómo se reparten los registros.",
                "registros de cada categoría ÷ total",
                f"SELECT {_q(c.nombre)}, count(*) AS registros, round(100.0 * count(*) / sum(count(*)) OVER (), 1) "
                f"AS porcentaje FROM {tabla} GROUP BY 1 ORDER BY registros DESC", c)

    # ------------------------------------------------------------------ territorio
    if territorios:
        t = territorios[0]
        agregar(f"Cobertura y ranking por {t.nombre}", "Territorio",
                "Identifica dónde se concentra la actividad y qué territorios tienen poca o ninguna.",
                f"registros por {t.nombre}",
                f"SELECT {_q(t.nombre)}, count(*) AS registros FROM {tabla} GROUP BY 1 ORDER BY registros DESC", t)

    # -------------------------------------------------------------------- magnitud
    for n in montos[:2]:
        agregar(f"Suma, promedio y mediana de {n.nombre}", "Magnitud",
                "Resume el nivel típico y el total de la variable numérica.",
                f"suma, promedio y mediana de {n.nombre}",
                f"SELECT sum({_q(n.nombre)}) AS suma, round(avg({_q(n.nombre)}), 2) AS promedio, "
                f"percentile_cont(0.5) WITHIN GROUP (ORDER BY {_q(n.nombre)}) AS mediana FROM {tabla}", n)
        if dimension:
            agregar(f"Promedio de {n.nombre} por {dimension.nombre}", "Magnitud",
                    "Compara la variable entre grupos para encontrar diferencias.",
                    f"promedio de {n.nombre} en cada {dimension.nombre}",
                    f"SELECT {_q(dimension.nombre)}, round(avg({_q(n.nombre)}), 2) AS promedio, count(*) AS registros "
                    f"FROM {tabla} GROUP BY 1 ORDER BY promedio DESC", n, dimension)

    return out[:MAX_SUGERENCIAS]
