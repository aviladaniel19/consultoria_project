"""
🧹 Módulo de Limpieza Avanzada de Datos
=======================================

Paquete modular para limpieza de datos reutilizable con cualquier
base de datos (CSV, Excel, SQL, etc.).

Clases principales:
    - AnalizadorDatos: análisis de tipos de variables y datos faltantes
    - ImputadorAvanzado: imputación KNN, MICE, interpolación, regresión
    - CorreccionFormatos: detección y corrección automática de fechas
    - LimpiadorCompleto: pipeline orquestador que combina todo
    - EvaluadorMetodos: comparación estadística de métodos de imputación

Funciones de visualización:
    - visualizar_comparacion_metodos: barras comparativas MAE/RMSE/R²/MAPE
    - visualizar_distribucion_errores: scatter, histograma y residuales
    - crear_heatmap_metricas: heatmap de métricas por método
"""

from .analizador import AnalizadorDatos
from .imputador import ImputadorAvanzado
from .formatos import CorreccionFormatos
from .limpiador import LimpiadorCompleto
from .evaluador import EvaluadorMetodos
from .visualizaciones import (
    visualizar_comparacion_metodos,
    visualizar_distribucion_errores,
    crear_heatmap_metricas,
)

__all__ = [
    'AnalizadorDatos',
    'ImputadorAvanzado',
    'CorreccionFormatos',
    'LimpiadorCompleto',
    'EvaluadorMetodos',
    'visualizar_comparacion_metodos',
    'visualizar_distribucion_errores',
    'crear_heatmap_metricas',
]

__version__ = '1.1.0'
