"""
Módulo de corrección de formatos.
"""

import pandas as pd
from typing import List, Optional


class CorreccionFormatos:
    """
    Clase para corrección de formatos, especialmente fechas.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()

    def corregir_fechas(
        self,
        columnas: Optional[List[str]] = None,
        formato: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Detecta y corrige formatos de fecha.
        """
        print("\n" + "=" * 70)
        print("📅 CORRECCIÓN DE FORMATOS DE FECHA")
        print("=" * 70)

        df_resultado = self.df.copy()

        if columnas is None:
            columnas = []
            for col in df_resultado.columns:
                if self._es_posible_fecha(df_resultado[col]):
                    columnas.append(col)

        for col in columnas:
            try:
                if formato:
                    df_resultado[col] = pd.to_datetime(
                        df_resultado[col], format=formato, errors='coerce'
                    )
                else:
                    df_resultado[col] = pd.to_datetime(
                        df_resultado[col], errors='coerce'
                    )

                n_convertidos = df_resultado[col].notna().sum()
                n_fallidos = df_resultado[col].isna().sum()
                print(
                    f"✅ '{col}': {n_convertidos} fechas convertidas, "
                    f"{n_fallidos} fallos"
                )

                if n_convertidos > 0:
                    min_fecha = df_resultado[col].min()
                    max_fecha = df_resultado[col].max()
                    print(f"   Rango: {min_fecha} a {max_fecha}")

            except Exception as e:
                print(f"❌ Error en '{col}': {str(e)}")

        self.df = df_resultado
        return df_resultado

    def _es_posible_fecha(self, serie: pd.Series) -> bool:
        if pd.api.types.is_datetime64_any_dtype(serie):
            return True
        if pd.api.types.is_numeric_dtype(serie):
            return False

        muestra = serie.dropna().head(50)
        if len(muestra) == 0:
            return False

        try:
            convertidos = pd.to_datetime(muestra, errors='coerce')
            pct_exitoso = convertidos.notna().sum() / len(muestra)
            return pct_exitoso > 0.5
        except Exception:
            return False
