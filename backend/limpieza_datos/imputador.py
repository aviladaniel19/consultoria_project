"""
Módulo de imputación avanzada de datos.
Contiene la clase ImputadorAvanzado con múltiples métodos de imputación:
KNN, MICE, interpolación, regresión lineal y eliminación de categóricos nulos.
"""

import pandas as pd
import numpy as np
from typing import List


class ImputadorAvanzado:
    """
    Clase para imputación de datos usando métodos estadísticos avanzados.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.df_original = df.copy()

    def imputar_knn(self, columnas: List[str], n_neighbors: int = 5) -> pd.DataFrame:
        """
        Imputa valores faltantes usando K-Nearest Neighbors.
        """
        from sklearn.impute import KNNImputer

        print("\n" + "=" * 70)
        print(f"🔧 IMPUTACIÓN KNN (k={n_neighbors})")
        print("=" * 70)

        df_numerico = self.df.select_dtypes(include=[np.number])
        imputer = KNNImputer(n_neighbors=n_neighbors, weights='distance')
        datos_imputados = imputer.fit_transform(df_numerico)

        df_resultado = self.df.copy()
        df_resultado[df_numerico.columns] = datos_imputados

        for col in columnas:
            if col in df_numerico.columns:
                n_imputados = self.df_original[col].isna().sum()
                if n_imputados > 0:
                    valor_medio_imputado = df_resultado.loc[
                        self.df_original[col].isna(), col
                    ].mean()
                    print(
                        f"✅ {col}: {n_imputados} valores imputados "
                        f"(media imputada: {valor_medio_imputado:.2f})"
                    )

        self.df = df_resultado
        return df_resultado

    def imputar_mice(self, columnas: List[str], max_iter: int = 10) -> pd.DataFrame:
        """
        Imputa valores usando MICE (Multivariate Imputation by Chained Equations).
        """
        from sklearn.experimental import enable_iterative_imputer  # noqa: F401
        from sklearn.impute import IterativeImputer

        print("\n" + "=" * 70)
        print(f"🔧 IMPUTACIÓN MICE (max_iter={max_iter})")
        print("=" * 70)

        df_numerico = self.df.select_dtypes(include=[np.number])
        imputer = IterativeImputer(max_iter=max_iter, random_state=42, verbose=0)
        datos_imputados = imputer.fit_transform(df_numerico)

        df_resultado = self.df.copy()
        df_resultado[df_numerico.columns] = datos_imputados

        for col in columnas:
            if col in df_numerico.columns:
                n_imputados = self.df_original[col].isna().sum()
                if n_imputados > 0:
                    valor_medio_imputado = df_resultado.loc[
                        self.df_original[col].isna(), col
                    ].mean()
                    print(
                        f"✅ {col}: {n_imputados} valores imputados "
                        f"(media imputada: {valor_medio_imputado:.2f})"
                    )

        self.df = df_resultado
        return df_resultado

    def imputar_interpolacion(
        self, columnas: List[str], metodo: str = 'linear'
    ) -> pd.DataFrame:
        """
        Imputa valores faltantes usando interpolación.
        """
        print("\n" + "=" * 70)
        print(f"🔧 IMPUTACIÓN POR INTERPOLACIÓN ({metodo})")
        print("=" * 70)

        df_resultado = self.df.copy()

        for col in columnas:
            if col in df_resultado.columns:
                n_imputados = df_resultado[col].isna().sum()
                if n_imputados > 0:
                    df_resultado[col] = df_resultado[col].interpolate(
                        method=metodo, limit_direction='both'
                    )
                    print(
                        f"✅ {col}: {n_imputados} valores imputados "
                        f"por interpolación {metodo}"
                    )

        self.df = df_resultado
        return df_resultado

    def imputar_regresion(self, columnas: List[str]) -> pd.DataFrame:
        """
        Imputa valores faltantes usando regresión lineal multivariable.
        """
        from sklearn.linear_model import LinearRegression

        print("\n" + "=" * 70)
        print("🔧 IMPUTACIÓN POR REGRESIÓN LINEAL")
        print("=" * 70)

        df_resultado = self.df.copy()

        for col in columnas:
            if col in df_resultado.columns and pd.api.types.is_numeric_dtype(
                df_resultado[col]
            ):
                n_imputados = df_resultado[col].isna().sum()

                if n_imputados > 0:
                    mask_completos = df_resultado[col].notna()
                    features = df_resultado.select_dtypes(
                        include=[np.number]
                    ).columns.drop(col)
                    features_sin_nulos = [
                        f for f in features if df_resultado[f].isna().sum() == 0
                    ]

                    if len(features_sin_nulos) > 0:
                        X_train = df_resultado.loc[mask_completos, features_sin_nulos]
                        y_train = df_resultado.loc[mask_completos, col]
                        X_pred = df_resultado.loc[~mask_completos, features_sin_nulos]

                        modelo = LinearRegression()
                        modelo.fit(X_train, y_train)
                        y_pred = modelo.predict(X_pred)
                        df_resultado.loc[~mask_completos, col] = y_pred

                        print(
                            f"✅ {col}: {n_imputados} valores imputados por regresión "
                            f"(R² = {modelo.score(X_train, y_train):.3f})"
                        )
                    else:
                        print(
                            f"⚠️ {col}: No hay suficientes features para regresión"
                        )

        self.df = df_resultado
        return df_resultado

    def eliminar_categoricos_nulos(
        self, umbral_porcentaje: float = 50.0
    ) -> pd.DataFrame:
        """
        Elimina filas/columnas con valores nulos en variables categóricas.
        """
        print("\n" + "=" * 70)
        print("🗑️  ELIMINACIÓN DE NULOS EN VARIABLES CATEGÓRICAS")
        print("=" * 70)

        df_resultado = self.df.copy()
        n_inicial = len(df_resultado)
        cols_categoricas = df_resultado.select_dtypes(
            include=['object', 'category']
        ).columns

        for col in cols_categoricas:
            pct_nulos = (df_resultado[col].isna().sum() / len(df_resultado)) * 100

            if pct_nulos > umbral_porcentaje:
                df_resultado = df_resultado.drop(columns=[col])
                print(f"🗑️  Columna '{col}' eliminada ({pct_nulos:.1f}% nulos)")
            elif pct_nulos > 0:
                n_nulos = df_resultado[col].isna().sum()
                df_resultado = df_resultado.dropna(subset=[col])
                print(
                    f"✅ '{col}': {n_nulos} filas eliminadas ({pct_nulos:.1f}% nulos)"
                )

        n_final = len(df_resultado)
        print(
            f"\n📊 Filas totales eliminadas: {n_inicial - n_final} "
            f"({((n_inicial - n_final) / n_inicial * 100):.1f}%)"
        )

        self.df = df_resultado
        return df_resultado
