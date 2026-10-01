"""
Módulo de evaluación de métodos de imputación.
Contiene la clase EvaluadorMetodos para comparar métodos usando
tests estadísticos (KS, Anderson-Darling) y métricas de error.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional

from .imputador import ImputadorAvanzado


class EvaluadorMetodos:
    """
    Clase para evaluar y comparar métodos de imputación usando tests estadísticos.
    """

    def __init__(self, df_original: pd.DataFrame):
        self.df_original = df_original.copy()
        self.resultados: Dict = {}

    def introducir_nulos_controlados(
        self, columnas: List[str], porcentaje: float = 20.0
    ) -> pd.DataFrame:
        """
        Introduce valores nulos de forma controlada para evaluar métodos.
        """
        df_con_nulos = self.df_original.copy()
        np.random.seed(42)

        for col in columnas:
            n_nulos = int(len(df_con_nulos) * porcentaje / 100)
            indices = np.random.choice(df_con_nulos.index, n_nulos, replace=False)
            df_con_nulos.loc[indices, col] = np.nan

        print(f"\n✅ Introducidos {porcentaje}% de nulos en {len(columnas)} columnas")
        return df_con_nulos

    def calcular_metricas_error(
        self,
        df_imputado: pd.DataFrame,
        columnas: List[str],
        mascara_nulos: pd.DataFrame,
    ) -> Dict:
        """
        Calcula métricas de error comparando valores imputados con originales.
        """
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

        metricas = {}

        for col in columnas:
            valores_originales = self.df_original.loc[mascara_nulos[col], col]
            valores_imputados = df_imputado.loc[mascara_nulos[col], col]

            mae = mean_absolute_error(valores_originales, valores_imputados)
            rmse = np.sqrt(mean_squared_error(valores_originales, valores_imputados))
            mape = (
                np.mean(
                    np.abs(
                        (valores_originales - valores_imputados) / valores_originales
                    )
                )
                * 100
            )
            r2 = r2_score(valores_originales, valores_imputados)
            bias = np.mean(valores_imputados - valores_originales)

            metricas[col] = {
                'MAE': mae,
                'RMSE': rmse,
                'MAPE': mape,
                'R2': r2,
                'Bias': bias,
                'n_valores': len(valores_originales),
            }

        return metricas

    def test_kolmogorov_smirnov(
        self, df_imputado: pd.DataFrame, columnas: List[str]
    ) -> Dict:
        """
        Test de Kolmogorov-Smirnov para comparar distribuciones.

        H0: Las distribuciones original e imputada son iguales.
        Si p_value > 0.05 → no rechazamos H0 → distribuciones similares.
        """
        from scipy.stats import ks_2samp

        resultados_ks = {}

        for col in columnas:
            valores_originales = self.df_original[col].dropna()
            valores_imputados = df_imputado[col].dropna()

            statistic, p_value = ks_2samp(valores_originales, valores_imputados)

            resultados_ks[col] = {
                'statistic': statistic,
                'p_value': p_value,
                'son_similares': p_value > 0.05,
            }

        return resultados_ks

    def test_anderson_darling(
        self, df_imputado: pd.DataFrame, columnas: List[str]
    ) -> Dict:
        """
        Test de Anderson-Darling para normalidad de los datos imputados.
        """
        from scipy.stats import anderson

        resultados_ad = {}

        for col in columnas:
            valores_imputados = df_imputado[col].dropna()
            result = anderson(valores_imputados)

            resultados_ad[col] = {
                'statistic': result.statistic,
                'critical_values': result.critical_values,
                'significance_level': result.significance_level,
                'es_normal': result.statistic < result.critical_values[2],  # 5%
            }

        return resultados_ad

    def comparar_metodos(
        self,
        columnas: List[str],
        porcentaje_nulos: float = 20.0,
        metodos: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Compara todos los métodos de imputación con tests estadísticos.
        """
        if metodos is None:
            metodos = ['knn', 'mice', 'regresion', 'interpolacion']

        print("\n" + "=" * 70)
        print("🔬 COMPARACIÓN ESTADÍSTICA DE MÉTODOS DE IMPUTACIÓN")
        print("=" * 70)

        # Introducir nulos controlados
        df_con_nulos = self.introducir_nulos_controlados(columnas, porcentaje_nulos)
        mascara_nulos = df_con_nulos[columnas].isna()

        comparacion = []

        for metodo in metodos:
            print(f"\n{'=' * 70}")
            print(f"Evaluando método: {metodo.upper()}")
            print(f"{'=' * 70}")

            try:
                imputador = ImputadorAvanzado(df_con_nulos)

                if metodo == 'knn':
                    df_imputado = imputador.imputar_knn(columnas, n_neighbors=5)
                elif metodo == 'mice':
                    df_imputado = imputador.imputar_mice(columnas, max_iter=10)
                elif metodo == 'regresion':
                    df_imputado = imputador.imputar_regresion(columnas)
                elif metodo == 'interpolacion':
                    df_imputado = imputador.imputar_interpolacion(
                        columnas, metodo='linear'
                    )
                else:
                    print(f"⚠️ Método '{metodo}' no reconocido, saltando.")
                    continue

                # Métricas de error
                metricas = self.calcular_metricas_error(
                    df_imputado, columnas, mascara_nulos
                )

                # Test de Kolmogorov–Smirnov
                ks_test = self.test_kolmogorov_smirnov(df_imputado, columnas)

                for col in columnas:
                    comparacion.append({
                        'Método': metodo.upper(),
                        'Columna': col,
                        'MAE': metricas[col]['MAE'],
                        'RMSE': metricas[col]['RMSE'],
                        'MAPE (%)': metricas[col]['MAPE'],
                        'R²': metricas[col]['R2'],
                        'Bias': metricas[col]['Bias'],
                        'KS p-value': ks_test[col]['p_value'],
                        'Dist. Similar': '✓' if ks_test[col]['son_similares'] else '✗',
                    })

            except Exception as e:
                print(f"❌ Error con método {metodo}: {str(e)}")

        df_comparacion = pd.DataFrame(comparacion)
        self.resultados['comparacion'] = df_comparacion
        return df_comparacion

    def recomendar_mejor_metodo(self, df_comparacion: pd.DataFrame) -> Dict:
        """
        Recomienda el mejor método basándose en un score compuesto ponderado.

        Pesos: MAE 30%, RMSE 30%, MAPE 20%, R² 20%.
        """
        print("\n" + "=" * 70)
        print("🏆 RECOMENDACIÓN DE MEJOR MÉTODO")
        print("=" * 70)

        recomendaciones = {}

        for columna in df_comparacion['Columna'].unique():
            df_col = df_comparacion[df_comparacion['Columna'] == columna].copy()

            # Normalizar métricas (menor es mejor para MAE, RMSE, MAPE)
            eps = 1e-10
            for metrica in ['MAE', 'RMSE', 'MAPE (%)']:
                rango = df_col[metrica].max() - df_col[metrica].min() + eps
                df_col[f'Score_{metrica}'] = 1 - (
                    (df_col[metrica] - df_col[metrica].min()) / rango
                )

            # Mayor es mejor para R²
            rango_r2 = df_col['R²'].max() - df_col['R²'].min() + eps
            df_col['Score_R2'] = (df_col['R²'] - df_col['R²'].min()) / rango_r2

            # Score compuesto
            df_col['Score_Total'] = (
                df_col['Score_MAE'] * 0.3
                + df_col['Score_RMSE'] * 0.3
                + df_col['Score_MAPE (%)'] * 0.2
                + df_col['Score_R2'] * 0.2
            )

            mejor = df_col.loc[df_col['Score_Total'].idxmax()]

            recomendaciones[columna] = {
                'mejor_metodo': mejor['Método'],
                'score_total': mejor['Score_Total'],
                'mae': mejor['MAE'],
                'rmse': mejor['RMSE'],
                'mape': mejor['MAPE (%)'],
                'r2': mejor['R²'],
            }

            print(f"\n📊 {columna}:")
            print(f"   🏅 Mejor método: {mejor['Método']}")
            print(f"   📈 Score total: {mejor['Score_Total']:.3f}")
            print(f"   📉 MAE: {mejor['MAE']:.4f}")
            print(f"   📉 RMSE: {mejor['RMSE']:.4f}")
            print(f"   📉 MAPE: {mejor['MAPE (%)']:.2f}%")
            print(f"   📈 R²: {mejor['R²']:.4f}")

        return recomendaciones
