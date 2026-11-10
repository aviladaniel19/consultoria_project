"""MinTicQualityEngine: evaluación automatizada de calidad según los lineamientos de MinTIC.

Base normativa:
- Guía de calidad e interoperabilidad de datos abiertos, v. 8 (MinTIC, 2025), en el marco del
  CONPES 4144 de 2025: 17 criterios de calidad y el Anexo 1 de errores frecuentes (ERR001-ERR022).
- ISO/IEC 25012: cada hallazgo se asigna a un criterio y cada criterio se califica de 0 a 10,
  como la herramienta de calidad del portal datos.gov.co.
- Ley 1712 de 2014, Ley 1581 de 2012 y guía de anonimización del DANE (confidencialidad).

La guía no define un puntaje global de 0 a 100 ni niveles de cumplimiento: los de este motor
(`UMBRALES`) son un criterio propio de la plataforma, configurable, y así se declara en el reporte.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence

import pandas as pd

from .catalogo import CRITERIOS, REVISION_MANUAL
from .modelos import (
    CambioCriterio,
    CriterioEvaluado,
    Etapa,
    Hallazgo,
    MetadatosDCAT,
    Nivel,
    ReporteCalidad,
    ReporteComparativo,
)
from .reglas import REGLAS, Regla
from .util import normalizar

log = logging.getLogger(__name__)

UMBRALES: tuple[tuple[float, Nivel], ...] = ((95.0, "Excelente"), (80.0, "Avanzado"), (60.0, "Básico"))
NOTA = ("Puntaje por criterio de 0 a 10 según la Guía de calidad e interoperabilidad de datos abiertos de MinTIC "
        "(v. 8, 2025) e ISO/IEC 25012. El puntaje global (promedio ponderado, 0-100) y los niveles "
        "(Excelente ≥ 95, Avanzado ≥ 80, Básico ≥ 60) son un criterio de la plataforma, no de la guía. "
        "Los códigos PD-… son comprobaciones propias.")
ORDEN_SEVERIDAD = {"error": 0, "advertencia": 1, "info": 2}


class MinTicQualityEngine:
    def __init__(self, reglas: Sequence[Regla] | None = None, pesos: Mapping[str, float] | None = None,
                 umbrales: Sequence[tuple[float, Nivel]] = UMBRALES) -> None:
        self.reglas = list(REGLAS if reglas is None else reglas)
        self.pesos = {c: 1.0 for c in CRITERIOS} | dict(pesos or {})
        self.umbrales = sorted(umbrales, reverse=True)

    # ------------------------------------------------------------------ evaluación
    def evaluar(self, df: pd.DataFrame, metadatos: MetadatosDCAT, etapa: Etapa = "antes",
                muestra: bool = False) -> ReporteCalidad:
        df = normalizar(df)
        hallazgos: list[Hallazgo] = []
        for regla in self.reglas:
            try:
                hallazgos += regla(df, metadatos)
            except Exception:  # una regla que falla no tumba la evaluación
                log.exception("falló la regla de calidad %s", getattr(regla, "__name__", regla))
        hallazgos.sort(key=lambda h: (ORDEN_SEVERIDAD[h.severidad], -h.penalizacion, h.codigo, h.ubicacion))

        criterios = []
        for criterio, peso in self.pesos.items():
            propios = [h for h in hallazgos if h.criterio == criterio]
            puntaje = max(0.0, 10.0 - sum(h.penalizacion for h in propios))
            criterios.append(CriterioEvaluado(criterio=criterio, puntaje=round(puntaje, 2), peso=peso,
                                              hallazgos=len(propios)))
        peso_total = sum(c.peso for c in criterios) or 1.0
        score = round(10 * sum(c.puntaje * c.peso for c in criterios) / peso_total, 1)
        return ReporteCalidad(
            etapa=etapa, filas=len(df), columnas=len(df.columns), muestra=muestra, score_global=score,
            nivel_cumplimiento=self._nivel(score, hallazgos), criterios_evaluados=criterios,
            hallazgos_errores=hallazgos, revision_manual=dict(REVISION_MANUAL), nota_metodologica=NOTA)

    def _nivel(self, score: float, hallazgos: Sequence[Hallazgo]) -> Nivel:
        if any(h.bloqueante for h in hallazgos):
            return "No Aprobado"
        return next((nivel for minimo, nivel in self.umbrales if score >= minimo), "No Aprobado")

    # ----------------------------------------------------------------- comparación
    @staticmethod
    def comparar(antes: ReporteCalidad, despues: ReporteCalidad,
                 equivalencias: Mapping[str, str] | None = None) -> ReporteComparativo:
        """Impacto de la limpieza. `equivalencias` traduce los nombres de columna de «antes» a los
        de «después» cuando la limpieza los renombra."""
        eq = dict(equivalencias or {})

        def clave(h: Hallazgo, traducir: bool) -> tuple[str, str]:
            if h.columna is None:
                return h.codigo, h.ubicacion
            return h.codigo, eq.get(h.columna, h.columna) if traducir else h.columna

        claves_antes = {clave(h, True) for h in antes.hallazgos_errores}
        claves_despues = {clave(h, False) for h in despues.hallazgos_errores}
        puntajes_despues = {c.criterio: c.puntaje for c in despues.criterios_evaluados}
        return ReporteComparativo(
            score_antes=antes.score_global, score_despues=despues.score_global,
            cambio_score=round(despues.score_global - antes.score_global, 1),
            nivel_antes=antes.nivel_cumplimiento, nivel_despues=despues.nivel_cumplimiento,
            filas_antes=antes.filas, filas_despues=despues.filas,
            criterios=[CambioCriterio(criterio=c.criterio, antes=c.puntaje,
                                      despues=puntajes_despues.get(c.criterio, c.puntaje),
                                      cambio=round(puntajes_despues.get(c.criterio, c.puntaje) - c.puntaje, 2))
                       for c in antes.criterios_evaluados],
            resueltos=[h for h in antes.hallazgos_errores if clave(h, True) not in claves_despues],
            nuevos=[h for h in despues.hallazgos_errores if clave(h, False) not in claves_antes],
            persistentes=[h for h in despues.hallazgos_errores if clave(h, False) in claves_antes])

    # -------------------------------------------------------------------- pipeline
    def ejecutar(self, df: pd.DataFrame, metadatos: MetadatosDCAT,
                 limpiar: Callable[[pd.DataFrame], pd.DataFrame],
                 equivalencias: Mapping[str, str] | None = None,
                 ) -> tuple[ReporteCalidad, ReporteCalidad, ReporteComparativo]:
        """Diagnóstico base -> limpieza -> diagnóstico final -> comparativo."""
        antes = self.evaluar(df, metadatos, "antes")
        despues = self.evaluar(limpiar(df), metadatos.renombrar(dict(equivalencias or {})), "despues")
        return antes, despues, self.comparar(antes, despues, equivalencias)
