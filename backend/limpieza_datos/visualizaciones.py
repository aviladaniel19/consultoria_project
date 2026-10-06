"""
Módulo de visualización para comparación de métodos de imputación.
Contiene funciones para crear gráficos comparativos, distribuciones
de errores y heatmaps de métricas.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Backend sin GUI: seguro dentro del servidor API
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Optional


def visualizar_comparacion_metodos(
    df_comparacion: pd.DataFrame, guardar_como: Optional[str] = None
):
    """
    Crea visualizaciones comparativas de los métodos de imputación.
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        'Comparación de Métodos de Imputación',
        fontsize=16,
        fontweight='bold',
    )

    # 1. MAE por método
    ax1 = axes[0, 0]
    df_pivot = df_comparacion.pivot_table(
        values='MAE', index='Columna', columns='Método'
    )
    df_pivot.plot(kind='bar', ax=ax1, width=0.8)
    ax1.set_title('MAE (Mean Absolute Error) - Menor es Mejor', fontweight='bold')
    ax1.set_ylabel('MAE')
    ax1.set_xlabel('Columna')
    ax1.legend(title='Método', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax1.grid(True, alpha=0.3)

    # 2. RMSE por método
    ax2 = axes[0, 1]
    df_pivot = df_comparacion.pivot_table(
        values='RMSE', index='Columna', columns='Método'
    )
    df_pivot.plot(kind='bar', ax=ax2, width=0.8)
    ax2.set_title(
        'RMSE (Root Mean Squared Error) - Menor es Mejor', fontweight='bold'
    )
    ax2.set_ylabel('RMSE')
    ax2.set_xlabel('Columna')
    ax2.legend(title='Método', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax2.grid(True, alpha=0.3)

    # 3. R² por método
    ax3 = axes[1, 0]
    df_pivot = df_comparacion.pivot_table(
        values='R²', index='Columna', columns='Método'
    )
    df_pivot.plot(kind='bar', ax=ax3, width=0.8)
    ax3.set_title('R² Score - Mayor es Mejor', fontweight='bold')
    ax3.set_ylabel('R²')
    ax3.set_xlabel('Columna')
    ax3.legend(title='Método', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax3.axhline(y=0.8, color='green', linestyle='--', alpha=0.5, label='Bueno (0.8)')
    ax3.grid(True, alpha=0.3)

    # 4. MAPE por método
    ax4 = axes[1, 1]
    df_pivot = df_comparacion.pivot_table(
        values='MAPE (%)', index='Columna', columns='Método'
    )
    df_pivot.plot(kind='bar', ax=ax4, width=0.8)
    ax4.set_title('MAPE (%) - Menor es Mejor', fontweight='bold')
    ax4.set_ylabel('MAPE (%)')
    ax4.set_xlabel('Columna')
    ax4.legend(title='Método', bbox_to_anchor=(1.05, 1), loc='upper left')
    ax4.grid(True, alpha=0.3)

    plt.tight_layout()

    if guardar_como:
        fig.savefig(guardar_como, dpi=150, bbox_inches='tight')
        print(f"✅ Figura guardada en: {guardar_como}")
    else:
        plt.show()


def visualizar_distribucion_errores(
    df_original: pd.DataFrame,
    df_imputado: pd.DataFrame,
    columna: str,
    metodo: str,
    mascara_nulos: pd.DataFrame,
    guardar_como: Optional[str] = None,
):
    """
    Visualiza la distribución de errores para un método específico.
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(
        f'Análisis de Errores: {metodo.upper()} - Columna: {columna}',
        fontsize=14,
        fontweight='bold',
    )

    valores_originales = df_original.loc[mascara_nulos[columna], columna]
    valores_imputados = df_imputado.loc[mascara_nulos[columna], columna]
    errores = valores_imputados - valores_originales

    # 1. Scatter plot: Original vs Imputado
    ax1 = axes[0]
    ax1.scatter(valores_originales, valores_imputados, alpha=0.6, s=50)
    min_val = min(valores_originales.min(), valores_imputados.min())
    max_val = max(valores_originales.max(), valores_imputados.max())
    ax1.plot(
        [min_val, max_val],
        [min_val, max_val],
        'r--',
        lw=2,
        label='Perfecta predicción',
    )
    ax1.set_xlabel('Valores Originales', fontsize=11)
    ax1.set_ylabel('Valores Imputados', fontsize=11)
    ax1.set_title('Original vs Imputado', fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # 2. Distribución de errores
    ax2 = axes[1]
    ax2.hist(errores, bins=30, edgecolor='black', alpha=0.7)
    ax2.axvline(x=0, color='red', linestyle='--', lw=2, label='Error = 0')
    ax2.axvline(
        x=errores.mean(),
        color='green',
        linestyle='-',
        lw=2,
        label=f'Media = {errores.mean():.2f}',
    )
    ax2.set_xlabel('Error (Imputado - Original)', fontsize=11)
    ax2.set_ylabel('Frecuencia', fontsize=11)
    ax2.set_title('Distribución de Errores', fontweight='bold')
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # 3. Residuales
    ax3 = axes[2]
    ax3.scatter(valores_imputados, errores, alpha=0.6, s=50)
    ax3.axhline(y=0, color='red', linestyle='--', lw=2)
    ax3.set_xlabel('Valores Imputados', fontsize=11)
    ax3.set_ylabel('Residuales', fontsize=11)
    ax3.set_title('Análisis de Residuales', fontweight='bold')
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()

    if guardar_como:
        fig.savefig(guardar_como, dpi=150, bbox_inches='tight')
        print(f"✅ Figura guardada en: {guardar_como}")
    else:
        plt.show()


def crear_heatmap_metricas(
    df_comparacion: pd.DataFrame, guardar_como: Optional[str] = None
):
    """
    Crea un heatmap de las métricas por método.
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(
        'Heatmap de Métricas por Método', fontsize=16, fontweight='bold'
    )

    metricas = ['MAE', 'RMSE', 'MAPE (%)', 'R²']

    for idx, metrica in enumerate(metricas):
        ax = axes[idx // 2, idx % 2]
        pivot = df_comparacion.pivot_table(
            values=metrica, index='Columna', columns='Método'
        )

        if metrica == 'R²':
            sns.heatmap(
                pivot,
                annot=True,
                fmt='.3f',
                cmap='RdYlGn',
                ax=ax,
                cbar_kws={'label': metrica},
                vmin=0,
                vmax=1,
            )
        else:
            sns.heatmap(
                pivot,
                annot=True,
                fmt='.3f',
                cmap='RdYlGn_r',
                ax=ax,
                cbar_kws={'label': metrica},
            )

        ax.set_title(f'{metrica}', fontweight='bold')
        ax.set_xlabel('Método')
        ax.set_ylabel('Columna')

    plt.tight_layout()

    if guardar_como:
        fig.savefig(guardar_como, dpi=150, bbox_inches='tight')
        print(f"✅ Figura guardada en: {guardar_como}")
    else:
        plt.show()
