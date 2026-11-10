# Análisis del anteproyecto

Material para reproducir las cifras del anteproyecto *Validación del Índice Global de Calidad
de datos.gov.co*.

| Archivo | Qué es |
| --- | --- |
| `datos/evaluacion_mintic_corte_2025-12-19.csv` | Evaluación de la Herramienta de Calidad de MinTIC: 8.299 conjuntos, corte del 19 dic 2025, descargada el 5 nov 2026 de <https://www.datos.gov.co/d/wa49-85xq>. Licencia CC BY-SA 4.0 |
| `datos/*.sha256` | Huella del archivo. El script se detiene si no coincide |
| `cifras_anteproyecto.py` | Calcula las cifras de la sección 1 del anteproyecto |

```bash
python analisis/cifras_anteproyecto.py            # cifras del índice con la copia local
python analisis/cifras_anteproyecto.py --casos    # además, DIVIPOLA y SECOP II en la API (requiere red)
python analisis/cifras_anteproyecto.py --descargar  # copia nueva y fechada, sin tocar la original
```

La copia original no se modifica nunca. Si MinTIC publica un corte nuevo, `--descargar` lo
guarda aparte con su fecha y su huella.
