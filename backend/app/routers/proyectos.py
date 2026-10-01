"""
proyectos.py — CRUD completo de Proyectos Vigía.

Endpoints:
  GET    /proyectos/              → listar proyectos
  POST   /proyectos/              → crear proyecto
  GET    /proyectos/{id}          → obtener proyecto por ID
  PUT    /proyectos/{id}          → actualizar proyecto
  DELETE /proyectos/{id}          → eliminar proyecto
  GET    /proyectos/{id}/indices  → calcular 4 índices Vigía
  GET    /proyectos/{id}/alertas  → listar alertas del proyecto
"""

import logging
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Proyecto, Indicador, Afirmacion, AlertaLog
from app.models.schemas import (
    ProyectoCreate, ProyectoUpdate, ProyectoResponse,
    ProyectoListResponse, IndiceVigiaResponse, AlertaListResponse,
)
from app.routers.auth import get_current_user

router = APIRouter(prefix="/proyectos", tags=["Proyectos"])
logger = logging.getLogger("vigia.proyectos")


# ── GET /proyectos/ ───────────────────────────────────

@router.get(
    "/",
    response_model=ProyectoListResponse,
    summary="Listar todos los proyectos",
)
def listar_proyectos(
    skip: int = Query(0, ge=0, description="Offset para paginación"),
    limit: int = Query(20, ge=1, le=100),
    estado: Optional[str] = Query(None, description="Filtrar por estado: ACTIVO, PAUSADO, CERRADO"),
    db: Session = Depends(get_db),
):
    query = db.query(Proyecto)
    if estado:
        query = query.filter(Proyecto.estado == estado.upper())
    total = query.count()
    proyectos = query.order_by(Proyecto.created_at.desc()).offset(skip).limit(limit).all()
    return ProyectoListResponse(total=total, proyectos=proyectos)


# ── POST /proyectos/ ──────────────────────────────────

@router.post(
    "/",
    response_model=ProyectoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo proyecto",
)
def crear_proyecto(
    payload: ProyectoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    proyecto = Proyecto(
        id=str(uuid.uuid4()),
        nombre=payload.nombre,
        descripcion=payload.descripcion,
        responsable=payload.responsable,
        fecha_inicio=payload.fecha_inicio,
        estado=payload.estado,
    )
    db.add(proyecto)
    db.commit()
    db.refresh(proyecto)
    logger.info(f"Proyecto creado: id={proyecto.id}, nombre='{proyecto.nombre}'")
    return proyecto


# ── GET /proyectos/{id} ───────────────────────────────

@router.get(
    "/{proyecto_id}",
    response_model=ProyectoResponse,
    summary="Obtener un proyecto por ID",
)
def obtener_proyecto(
    proyecto_id: str,
    db: Session = Depends(get_db),
):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")
    return proyecto


# ── PUT /proyectos/{id} ───────────────────────────────

@router.put(
    "/{proyecto_id}",
    response_model=ProyectoResponse,
    summary="Actualizar un proyecto",
)
def actualizar_proyecto(
    proyecto_id: str,
    payload: ProyectoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(proyecto, field, value)

    db.commit()
    db.refresh(proyecto)
    logger.info(f"Proyecto actualizado: id={proyecto_id}")
    return proyecto


# ── DELETE /proyectos/{id} ────────────────────────────

@router.delete(
    "/{proyecto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un proyecto",
)
def eliminar_proyecto(
    proyecto_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")
    db.delete(proyecto)
    db.commit()
    logger.info(f"Proyecto eliminado: id={proyecto_id}")


# ── GET /proyectos/{id}/indices ───────────────────────

@router.get(
    "/{proyecto_id}/indices",
    response_model=IndiceVigiaResponse,
    summary="Calcular los 4 índices Vigía del proyecto",
    description=(
        "**Índice de Avance**: promedio de (valor_real/valor_meta)*100 de todos los indicadores.\n\n"
        "**Índice de Capacidad**: fracción de indicadores con valor_real registrado.\n\n"
        "**Índice de Veracidad**: afirmaciones SUSTENTADAS / total afirmaciones contrastadas.\n\n"
        "**Índice de Impacto**: placeholder (requiere campo beneficiarios)."
    ),
)
def calcular_indices(
    proyecto_id: str,
    db: Session = Depends(get_db),
):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")

    indicadores = db.query(Indicador).filter(Indicador.proyecto_id == proyecto_id).all()
    afirmaciones = db.query(Afirmacion).filter(Afirmacion.proyecto_id == proyecto_id).all()

    # Índice de Avance
    avances = []
    for ind in indicadores:
        if ind.valor_meta and ind.valor_meta > 0 and ind.valor_real is not None:
            avances.append(min((ind.valor_real / ind.valor_meta) * 100, 100))
    indice_avance = round(sum(avances) / len(avances), 2) if avances else None

    # Índice de Capacidad
    total_ind = len(indicadores)
    con_valor = sum(1 for i in indicadores if i.valor_real is not None)
    indice_capacidad = round((con_valor / total_ind) * 100, 2) if total_ind > 0 else None

    # Índice de Veracidad
    contrastadas = [a for a in afirmaciones if a.veredicto is not None]
    sustentadas = [a for a in contrastadas if a.veredicto == "SUSTENTADA"]
    indice_veracidad = round((len(sustentadas) / len(contrastadas)) * 100, 2) if contrastadas else None

    return IndiceVigiaResponse(
        proyecto_id=proyecto_id,
        indice_avance=indice_avance,
        indice_impacto=None,  # Se implementa en Semana 6 con Agente 02
        indice_capacidad=indice_capacidad,
        indice_veracidad=indice_veracidad,
    )


# ── GET /proyectos/{id}/alertas ───────────────────────

@router.get(
    "/{proyecto_id}/alertas",
    response_model=AlertaListResponse,
    summary="Listar alertas del proyecto",
)
def listar_alertas_proyecto(
    proyecto_id: str,
    db: Session = Depends(get_db),
):
    proyecto = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not proyecto:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")

    alertas = (
        db.query(AlertaLog)
        .filter(AlertaLog.proyecto_id == proyecto_id)
        .order_by(AlertaLog.timestamp.desc())
        .limit(50)
        .all()
    )
    return AlertaListResponse(total=len(alertas), alertas=alertas)
