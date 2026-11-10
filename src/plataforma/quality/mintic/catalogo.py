"""Catálogo de errores del Anexo 1 de la «Guía de calidad e interoperabilidad de datos abiertos»
(MinTIC, versión 8, mayo de 2025), con el criterio ISO/IEC 25012 al que afecta cada uno.

Los códigos PD-… no existen en la guía: son comprobaciones propias de la plataforma que
amplían un criterio, y así se declaran en el reporte.
"""
from __future__ import annotations

from typing import NamedTuple


class Error(NamedTuple):
    tipo: str
    criterio: str
    recomendacion: str


HERRAMIENTAS = ("Usar herramientas de calidad de datos para estandarizar los campos e identificar los "
                "errores presentados.")

ERRORES: dict[str, Error] = {
    "ERR001": Error("Título y descripción mal nombrados", "Comprensibilidad",
                    "Actualizar el título y la descripción: completos, generales, sin siglas, caracteres "
                    "especiales ni vigencias."),
    "ERR002": Error("Metadata vacía o incompleta", "Credibilidad",
                    "Actualizar o incluir en la metadata del conjunto los campos faltantes."),
    "ERR003": Error("El usuario publicador debe ser la entidad", "Credibilidad",
                    "Diligenciar el nombre de la entidad, no el de un funcionario, y usar un correo institucional."),
    "ERR004": Error("Conjunto de datos sin filas", "Conformidad",
                    "Eliminar el conjunto y crear uno que contenga columnas y filas con información."),
    "ERR005": Error("Conjunto de datos con pocas filas (menos de 50)", "Conformidad",
                    "Aumentar el número de registros, agregar columnas o consolidar con otras bases "
                    "complementarias o históricas."),
    "ERR007": Error("Filas, columnas o celdas vacías", "Completitud", HERRAMIENTAS),
    "ERR008": Error("Conjunto de datos con una sola columna", "Conformidad",
                    "Eliminar el conjunto y crear uno con columnas y filas que lo complementen."),
    "ERR008_1": Error("Conjunto de datos con pocas columnas (menos de 5)", "Conformidad",
                      "Mejorar la completitud del conjunto agregando nuevas columnas."),
    "ERR008_2": Error("Columnas mal nombradas o sin nombre", "Comprensibilidad", HERRAMIENTAS),
    "ERR008_3": Error("Columnas sin descripción en la metadata", "Comprensibilidad",
                      "Asignar una descripción a cada columna en la metadata."),
    "ERR009": Error("Dirección sin columnas de geolocalización", "Consistencia",
                    "Incluir campos de geolocalización (latitud y longitud) para que los usuarios puedan "
                    "hacer mapas de ubicación."),
    "ERR011": Error("Conjunto clasificado por periodos (vigencias) o tipologías", "Conformidad",
                    "Crear un solo conjunto de datos e incluir una columna de periodo (vigencia o fecha), "
                    "consolidando los registros de todos los años."),
    "ERR014": Error("Conjunto de datos desactualizado", "Actualidad",
                    "Actualizar el conjunto según su «Frecuencia de actualización»."),
    "ERR016": Error("Datos agregados o totalizados", "Conformidad",
                    "Publicar la fuente detallada, en su máximo nivel de desagregación, y usar vistas "
                    "filtradas para los reportes."),
    "ERR017": Error("Falta de comprensibilidad", "Comprensibilidad",
                    "Mejorar los metadatos con el contexto que da sentido, propósito y uso a los datos."),
    "ERR018": Error("El conjunto contiene datos personales", "Confidencialidad",
                    "Aplicar técnicas de anonimización antes de publicar (guía de anonimización del DANE; "
                    "Ley 1581 de 2012 y Ley 1712 de 2014)."),
    "ERR019": Error("Error en los tipos de datos", "Exactitud",
                    "Estandarizar los tipos de datos de acuerdo con las variables de cada columna."),
    "ERR020": Error("Falta de unicidad: registros duplicados", "Unicidad",
                    "Eliminar los registros duplicados con herramientas de calidad de datos como OpenRefine."),
    # --- comprobaciones propias de la plataforma (sin código en la guía)
    "PD-COL-REDUNDANTE": Error("Columnas con el mismo contenido y distinto nombre", "Eficiencia",
                               "Consolidar las columnas duplicadas en una sola (criterio de consistencia de la guía)."),
    "PD-COL-CONSTANTE": Error("Columna con un único valor en todos los registros", "Precisión",
                              "Revisar si la columna aporta información; si es fija, documentarla en la descripción."),
    "PD-GEO-RANGO": Error("Coordenadas fuera del territorio de Colombia", "Consistencia",
                          "Revisar latitud y longitud: en grados decimales, con punto decimal y sin intercambiar."),
}

# Errores de la guía que dependen del portal o de una revisión humana.
REVISION_MANUAL: dict[str, str] = {
    "ERR006": "Conjuntos obligatorios de la Ley 1712 de 2014 y el Decreto 103 de 2015",
    "ERR010": "Enlace externo en formato no válido",
    "ERR012": "El conjunto es una vista o filtro de un dato abierto nacional",
    "ERR013": "Conjunto mal estandarizado en la publicación",
    "ERR015": "Conjuntos con estructura similar de la misma entidad",
    "ERR021": "Poca reutilización por la academia, empresas, entidades y ciudadanos",
    "ERR022": "Vista, filtro o gráfica de un conjunto privado",
}

CRITERIOS: tuple[str, ...] = ("Comprensibilidad", "Credibilidad", "Actualidad", "Conformidad", "Completitud",
                              "Unicidad", "Eficiencia", "Exactitud", "Precisión", "Consistencia",
                              "Confidencialidad")
