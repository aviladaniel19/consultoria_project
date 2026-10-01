"""
Módulo orquestador de limpieza.
Contiene la clase LimpiadorCompleto que combina análisis, imputación,
corrección de formatos y eliminación de nulos en un pipeline unificado.
"""

import pandas as pd
from typing import Dict, List

from .analizador import AnalizadorDatos
from .imputador import ImputadorAvanzado
from .formatos import CorreccionFormatos


class LimpiadorCompleto:
    """
    Clase orquestadora que combina todos los métodos de limpieza.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.df_original = df.copy()
        self.historial: List[str] = []

    def pipeline_completo(
        self,
        metodo_imputacion: str = 'knn',
        eliminar_nulos_categoricos: bool = True,
        corregir_fechas: bool = True,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Ejecuta el pipeline completo de limpieza.
        """
        print("\n" + "=" * 70)
        print("🚀 INICIANDO PIPELINE DE LIMPIEZA COMPLETO")
        print("=" * 70)

        # 1. Análisis inicial
        analizador = AnalizadorDatos(self.df)
        reporte = analizador.generar_reporte_completo()
        clasificacion = reporte['clasificacion']

        # 2. Corrección de fechas
        if corregir_fechas and len(clasificacion['fechas']) > 0:
            corrector = CorreccionFormatos(self.df)
            self.df = corrector.corregir_fechas()
            self.historial.append("Fechas corregidas")

        # 3. Imputación numérica
        cols_numericas = (
            clasificacion['numericas_continuas']
            + clasificacion['numericas_discretas']
        )
        cols_con_nulos = [
            col for col in cols_numericas if self.df[col].isna().sum() > 0
        ]

        if len(cols_con_nulos) > 0:
            imputador = ImputadorAvanzado(self.df)

            if metodo_imputacion == 'knn':
                n_neighbors = kwargs.get('n_neighbors', 5)
                self.df = imputador.imputar_knn(
                    cols_con_nulos, n_neighbors=n_neighbors
                )
            elif metodo_imputacion == 'mice':
                max_iter = kwargs.get('max_iter', 10)
                self.df = imputador.imputar_mice(
                    cols_con_nulos, max_iter=max_iter
                )
            elif metodo_imputacion == 'interpolacion':
                metodo = kwargs.get('metodo_interpolacion', 'linear')
                self.df = imputador.imputar_interpolacion(
                    cols_con_nulos, metodo=metodo
                )
            elif metodo_imputacion == 'regresion':
                self.df = imputador.imputar_regresion(cols_con_nulos)

            self.historial.append(f"Imputación {metodo_imputacion} aplicada")

        # 4. Eliminación de nulos categóricos
        if eliminar_nulos_categoricos:
            imputador = ImputadorAvanzado(self.df)
            umbral = kwargs.get('umbral_categoricos', 50.0)
            self.df = imputador.eliminar_categoricos_nulos(
                umbral_porcentaje=umbral
            )
            self.historial.append("Nulos categóricos eliminados")

        self._resumen_final()
        return self.df

    def _resumen_final(self):
        """Imprime resumen final de la limpieza."""
        print("\n" + "=" * 70)
        print("📊 RESUMEN FINAL DE LIMPIEZA")
        print("=" * 70)
        print(f"\n🔸 Filas originales: {len(self.df_original):,}")
        print(f"🔸 Filas finales: {len(self.df):,}")
        print(f"🔸 Filas eliminadas: {len(self.df_original) - len(self.df):,}")
        print(f"\n🔸 Columnas originales: {len(self.df_original.columns)}")
        print(f"🔸 Columnas finales: {len(self.df.columns)}")

        nulos_originales = self.df_original.isna().sum().sum()
        nulos_finales = self.df.isna().sum().sum()
        print(f"\n🔸 Nulos originales: {nulos_originales:,}")
        print(f"🔸 Nulos finales: {nulos_finales:,}")
        reduccion = (
            (nulos_originales - nulos_finales) / max(nulos_originales, 1) * 100
        )
        print(f"🔸 Reducción de nulos: {reduccion:.1f}%")
        print("\n✅ Pipeline de limpieza completado")
