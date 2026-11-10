"""Modelos del motor de calidad MinTIC: metadatos de entrada, hallazgos y reportes."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Severidad = Literal["error", "advertencia", "info"]
Nivel = Literal["No Aprobado", "Básico", "Avanzado", "Excelente"]
Etapa = Literal["antes", "despues"]


class MetadatosDCAT(BaseModel):
    """Metadatos del conjunto, con los campos de DCAT que pide el portal datos.gov.co."""
    titulo: str = ""                       # dct:title
    descripcion: str = ""                  # dct:description
    entidad: str | None = None             # dct:publisher
    correo: str | None = None              # dcat:contactPoint
    usuario_publicador: str | None = None  # nombre de usuario que publica (ERR003)
    categoria: str | None = None           # dcat:theme
    frecuencia: str | None = None          # dct:accrualPeriodicity
    cobertura: str | None = None           # dct:spatial
    licencia: str | None = None            # dct:license
    etiquetas: list[str] = Field(default_factory=list)                 # dcat:keyword
    descripciones_columnas: dict[str, str] = Field(default_factory=dict)
    ultima_actualizacion: datetime | None = None                       # dct:modified
    llave: list[str] = Field(default_factory=list)                     # columnas que identifican cada fila

    def renombrar(self, equivalencias: dict[str, str]) -> MetadatosDCAT:
        """Los mismos metadatos con los nombres de columna que deja la limpieza."""
        return self.model_copy(update={
            "descripciones_columnas": {equivalencias.get(c, c): d for c, d in self.descripciones_columnas.items()},
            "llave": [equivalencias.get(c, c) for c in self.llave]})


class Hallazgo(BaseModel):
    codigo: str                 # ERRxxx de la guía de MinTIC, o PD-… si es una comprobación propia
    criterio: str               # criterio ISO/IEC 25012 al que afecta
    severidad: Severidad
    ubicacion: str              # «conjunto», «metadatos: título», «columna «x»»…
    columna: str | None = None
    mensaje: str
    recomendacion: str          # recomendación de la guía de MinTIC
    afectados: int = 0          # filas, celdas o columnas afectadas
    tasa: float | None = None   # proporción afectada (0-1), cuando aplica
    penalizacion: float = 0.0   # puntos (0-10) que resta a su criterio
    bloqueante: bool = False    # deja el conjunto en «No Aprobado» sin importar el puntaje


class CriterioEvaluado(BaseModel):
    criterio: str
    puntaje: float              # 0-10, como la herramienta de calidad del portal
    peso: float
    hallazgos: int


class ReporteCalidad(BaseModel):
    etapa: Etapa
    filas: int
    columnas: int
    muestra: bool = False       # True si se evaluó una muestra aleatoria y no todas las filas
    score_global: float         # 0-100
    nivel_cumplimiento: Nivel
    criterios_evaluados: list[CriterioEvaluado]
    hallazgos_errores: list[Hallazgo]
    revision_manual: dict[str, str] = Field(default_factory=dict)   # códigos que no se pueden automatizar
    nota_metodologica: str = ""


class CambioCriterio(BaseModel):
    criterio: str
    antes: float
    despues: float
    cambio: float


class ReporteComparativo(BaseModel):
    """Impacto de la limpieza: el mismo motor, antes y después."""
    score_antes: float
    score_despues: float
    cambio_score: float
    nivel_antes: Nivel
    nivel_despues: Nivel
    filas_antes: int
    filas_despues: int
    criterios: list[CambioCriterio]
    resueltos: list[Hallazgo]       # estaban antes y ya no
    nuevos: list[Hallazgo]          # aparecieron con la limpieza
    persistentes: list[Hallazgo]    # siguen después (en su versión «después»)
