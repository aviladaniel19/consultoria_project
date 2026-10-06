"""
datasets.py — Carga y análisis estadístico de datasets.

Endpoints:
  GET    /datasets/                → listar datasets registrados
  POST   /datasets/upload          → subir CSV/Excel y analizar
  GET    /datasets/{nombre}/info   → resumen rápido de un dataset
  POST   /datasets/{nombre}/analizar → análisis estadístico completo
  DELETE /datasets/{nombre}        → eliminar dataset
"""

import io
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Dataset
from app.models.schemas import DatasetResponse, DatasetAnalisisResponse
from app.routers.auth import get_current_user

router = APIRouter(prefix="/datasets", tags=["Datasets"])
logger = logging.getLogger("vigia.datasets")

# Directorio local donde se almacenan los CSV subidos
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── GET /datasets/ ────────────────────────────────────

@router.get(
    "/",
    response_model=list[DatasetResponse],
    summary="Listar datasets disponibles",
)
def listar_datasets(
    proyecto_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Dataset)
    if proyecto_id:
        query = query.filter(Dataset.proyecto_id == proyecto_id)
    return query.order_by(Dataset.created_at.desc()).all()


# ── POST /datasets/upload ─────────────────────────────

@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir un archivo CSV o Excel",
    description="Sube el archivo, lo guarda localmente y registra el dataset en la BD.",
)
async def subir_dataset(
    file: UploadFile = File(..., description="Archivo CSV o Excel"),
    descripcion: str = Form(default=""),
    proyecto_id: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="El archivo no tiene nombre")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".csv", ".xlsx", ".xls"):
        raise HTTPException(
            status_code=400,
            detail=f"Formato no soportado: '{ext}'. Use CSV o Excel.",
        )

    # Guardar en disco
    dest = DATA_DIR / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Registrar en BD
    dataset = Dataset(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id or None,
        nombre=file.filename,
        descripcion=descripcion,
        s3_path=str(dest),
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    logger.info(f"Dataset subido: '{file.filename}' ({len(content)/1024:.1f} KB)")
    return dataset


# ── GET /datasets/{nombre}/info ───────────────────────

@router.get(
    "/{nombre}/info",
    summary="Resumen rápido de un dataset",
)
def info_dataset(nombre: str):
    path = DATA_DIR / nombre
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{nombre}' no encontrado en disco")

    df = _cargar_dataframe(path)
    return {
        "nombre": nombre,
        "n_filas": len(df),
        "n_columnas": len(df.columns),
        "columnas": list(df.columns),
        "memoria_mb": round(df.memory_usage(deep=True).sum() / 1024**2, 3),
        # to_json convierte NaN/NaT a null (json.dumps falla con NaN)
        "muestra": json.loads(df.head(5).to_json(orient="records", date_format="iso")),
    }


# ── POST /datasets/{nombre}/analizar ─────────────────

@router.post(
    "/{nombre}/analizar",
    response_model=DatasetAnalisisResponse,
    summary="Análisis estadístico completo del dataset",
    description=(
        "Ejecuta el módulo `limpieza_datos` para identificar tipos de variables, "
        "datos faltantes y patrones de missingness."
    ),
)
def analizar_dataset(nombre: str):
    path = DATA_DIR / nombre
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Dataset '{nombre}' no encontrado en disco")

    df = _cargar_dataframe(path)

    # Usar el módulo de limpieza_datos
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from limpieza_datos.analizador import AnalizadorDatos

    analizador = AnalizadorDatos(df)
    clasificacion = analizador.identificar_tipos_variables()
    df_faltantes = analizador.analizar_datos_faltantes()

    # Construir respuesta de columnas
    columnas_info = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        n_nulos = int(df[col].isna().sum())
        pct_nulos = round(n_nulos / len(df) * 100, 2) if len(df) > 0 else 0
        tipo_vigia = _tipo_a_categoria(col, clasificacion)
        columnas_info.append({
            "nombre": col,
            "dtype": dtype,
            "tipo_vigia": tipo_vigia,
            "n_nulos": n_nulos,
            "pct_nulos": pct_nulos,
            "n_unicos": int(df[col].nunique()),
        })

    # Datos faltantes
    faltantes = []
    if len(df_faltantes) > 0 and hasattr(df_faltantes, "iterrows"):
        for _, row in df_faltantes.iterrows():
            faltantes.append({
                "columna": row.get("columna", ""),
                "n_nulos": int(row.get("n_nulos", 0)),
                "pct_nulos": round(float(row.get("pct_nulos", 0)), 2),
                "patron": row.get("patron", ""),
                "tipo": row.get("tipo", ""),
            })

    # Recomendaciones básicas
    recomendaciones = _generar_recomendaciones(df, clasificacion, faltantes)

    return DatasetAnalisisResponse(
        nombre=nombre,
        n_filas=len(df),
        n_columnas=len(df.columns),
        memoria_mb=round(df.memory_usage(deep=True).sum() / 1024**2, 3),
        columnas=columnas_info,
        datos_faltantes=faltantes,
        patron_missingness=analizador._test_mcar() if hasattr(analizador, "_test_mcar") else "N/A",
        recomendaciones=recomendaciones,
    )


# ── DELETE /datasets/{nombre} ─────────────────────────

@router.delete(
    "/{nombre}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar dataset",
)
def eliminar_dataset(
    nombre: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    path = DATA_DIR / nombre
    if path.exists():
        path.unlink()

    ds = db.query(Dataset).filter(Dataset.nombre == nombre).first()
    if ds:
        db.delete(ds)
        db.commit()
    logger.info(f"Dataset eliminado: '{nombre}'")


# ── Helpers ───────────────────────────────────────────

def _cargar_dataframe(path: Path) -> pd.DataFrame:
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        else:
            return pd.read_excel(path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"No se pudo leer el archivo: {e}")


def _tipo_a_categoria(col: str, clasificacion: dict) -> str:
    for tipo, cols in clasificacion.items():
        if col in cols:
            return tipo
    return "desconocido"


def _generar_recomendaciones(df: pd.DataFrame, clasificacion: dict, faltantes: list) -> list[str]:
    recs = []
    if faltantes:
        alta = [f for f in faltantes if f["pct_nulos"] > 30]
        if alta:
            nombres = [f["columna"] for f in alta]
            recs.append(
                f"⚠️ {len(alta)} columna(s) con >30% de nulos: {', '.join(nombres)}. "
                "Considere eliminar o usar imputación múltiple (MICE)."
            )
    if len(df) < 100:
        recs.append("📉 Dataset pequeño (<100 filas). Los resultados estadísticos pueden ser poco confiables.")
    if len(clasificacion.get("numericas_continuas", [])) == 0:
        recs.append("ℹ️ No se detectaron variables numéricas continuas. Verifica los tipos de columnas.")
    if not recs:
        recs.append("✅ Dataset en buen estado. Puedes proceder con la imputación.")
    return recs
