"""
Módulo de análisis de datos.
Contiene la clase AnalizadorDatos para identificar tipos de variables
y analizar patrones de datos faltantes.
"""

import pandas as pd
import numpy as np
from typing import Dict, List


class AnalizadorDatos:
    """
    Clase para identificar y analizar tipos de variables y datos faltantes.

    """

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.reporte: Dict = {}

    def identificar_tipos_variables(self) -> Dict[str, List[str]]:
        print("\n" + "=" * 70)
        print("🔍 ANÁLISIS DE TIPOS DE VARIABLES")
        print("=" * 70)

        clasificacion: Dict[str, List[str]] = {
            'numericas_continuas': [],
            'numericas_discretas': [],
            'categoricas_nominales': [],
            'categoricas_ordinales': [],
            'fechas': [],
            'texto': [],
            'booleanas': [],
        }

        for col in self.df.columns:
            tipo_detectado = self._detectar_tipo_variable(col)
            clasificacion[tipo_detectado].append(col)

        # Imprimir reporte
        for tipo, columnas in clasificacion.items():
            if columnas:
                print(f"\n📊 {tipo.upper().replace('_', ' ')}: {len(columnas)}")
                for col in columnas:
                    stats = self._estadisticas_columna(col)
                    print(f"   • {col}: {stats}")

        self.reporte['clasificacion'] = clasificacion
        return clasificacion

    def _detectar_tipo_variable(self, col: str) -> str:
        serie = self.df[col]

        if self._es_fecha(serie):
            return 'fechas'

        if serie.dtype == bool or set(serie.dropna().unique()).issubset(
            {0, 1, True, False, 'True', 'False', 'true', 'false'}
        ):
            return 'booleanas'

        if pd.api.types.is_numeric_dtype(serie):
            valores_unicos = serie.nunique()
            n_total = len(serie.dropna())
            if n_total == 0:
                return 'numericas_discretas'

            if valores_unicos < 10 or valores_unicos / n_total < 0.05:
                return 'numericas_discretas'
            else:
                if serie.dtype in ['int64', 'int32'] and valores_unicos < n_total * 0.5:
                    return 'numericas_discretas'
                return 'numericas_continuas'
        else:
            valores_unicos = serie.nunique()
            if valores_unicos < 20:
                return 'categoricas_nominales'
            elif valores_unicos < 50:
                return 'categoricas_ordinales'
            else:
                return 'texto'

    def _es_fecha(self, serie: pd.Series) -> bool:
        if pd.api.types.is_datetime64_any_dtype(serie):
            return True
        if pd.api.types.is_numeric_dtype(serie):
            return False
        try:
            muestra = serie.dropna().head(100)
            if len(muestra) > 0:
                convertidos = pd.to_datetime(muestra, errors='coerce')
                pct_exitoso = convertidos.notna().sum() / len(muestra)
                return pct_exitoso > 0.5
        except Exception:
            pass
        return False

    def _estadisticas_columna(self, col: str) -> str:
        serie = self.df[col]
        n_valores = len(serie)
        n_nulos = serie.isna().sum()
        n_unicos = serie.nunique()
        pct_nulos = (n_nulos / n_valores) * 100 if n_valores > 0 else 0

        if pd.api.types.is_numeric_dtype(serie):
            return (
                f"Únicos={n_unicos}, Nulos={n_nulos} ({pct_nulos:.1f}%), "
                f"Rango=[{serie.min():.2f}, {serie.max():.2f}]"
            )
        else:
            return f"Únicos={n_unicos}, Nulos={n_nulos} ({pct_nulos:.1f}%)"

    def analizar_datos_faltantes(self) -> pd.DataFrame:
        print("\n" + "=" * 70)
        print("📉 ANÁLISIS DE DATOS FALTANTES")
        print("=" * 70)

        analisis = []

        for col in self.df.columns:
            n_nulos = self.df[col].isna().sum()
            pct_nulos = (n_nulos / len(self.df)) * 100

            if n_nulos > 0:
                patron = self._detectar_patron_missingness(col)
                analisis.append({
                    'columna': col,
                    'n_nulos': n_nulos,
                    'pct_nulos': pct_nulos,
                    'patron': patron,
                    'tipo': self._detectar_tipo_variable(col),
                })

        df_analisis = pd.DataFrame(analisis)
        if len(df_analisis) > 0:
            df_analisis = df_analisis.sort_values('pct_nulos', ascending=False)
            print("\n📋 Resumen de Datos Faltantes:")
            print(df_analisis.to_string(index=False))
            print(f"\n🔬 Patrón de Missingness: {self._test_mcar()}")
        else:
            print("\n✅ No se detectaron datos faltantes")

        self.reporte['datos_faltantes'] = df_analisis
        return df_analisis

    def _detectar_patron_missingness(self, col: str) -> str:
        mascara_nulos = self.df[col].isna()
        correlaciones = []

        for otra_col in self.df.columns:
            if otra_col != col and pd.api.types.is_numeric_dtype(self.df[otra_col]):
                corr = np.corrcoef(
                    mascara_nulos.astype(float),
                    self.df[otra_col].fillna(0),
                )[0, 1]
                if abs(corr) > 0.3:
                    correlaciones.append((otra_col, corr))

        if len(correlaciones) > 0:
            return "MAR (posiblemente)"
        else:
            return "MCAR (posiblemente)"

    def _test_mcar(self) -> str:
        """Test simplificado de Little para MCAR."""
        nulos_por_fila = self.df.isna().sum(axis=1)
        varianza = nulos_por_fila.var()

        if varianza < 1:
            return "Probable (baja varianza en distribución de nulos)"
        else:
            return "Improbable (alta varianza sugiere patrón estructurado)"

    def generar_reporte_completo(self) -> Dict:
        """Genera un reporte completo del análisis."""
        self.identificar_tipos_variables()
        self.analizar_datos_faltantes()

        print("\n" + "=" * 70)
        print("📊 RESUMEN GENERAL")
        print("=" * 70)
        print(f"Filas: {len(self.df):,}")
        print(f"Columnas: {len(self.df.columns)}")
        print(f"Memoria: {self.df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

        return self.reporte
