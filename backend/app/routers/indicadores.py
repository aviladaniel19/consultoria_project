"""
indicadores.py — CRUD de Indicadores por Proyecto.

Endpoints:
  GET    /proyectos/{id}/indicadores/          → listar indicadores del proyecto
  POST   /proyectos/{id}/indicadores/          → crear indicador
  PUT    /proyectos/{id}/indicadores/{ind_id}  → actualizar valor del indicador
  DELETE /proyectos/{id}/indicadores/{ind_id}  → eliminar indicador
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import Proyecto, Indicador
from app.models.schemas import (
    IndicadorCreate, IndicadorUpdate, IndicadorResponse,
)
from app.routers.auth import get_current_user

router = APIRouter(prefix="/proyectos", tags=["Indicadores"])
logger = logging.getLogger("vigia.indicadores")


# ── GET /proyectos/{id}/indicadores/ ─────────────────

@router.get(
    "/{proyecto_id}/indicadores/",
    response_model=list[IndicadorResponse],
    summary="Listar indicadores del proyecto",
)
def listar_indicadores(
    proyecto_id: str,
    db: Session = Depends(get_db),
):
    _check_proyecto(proyecto_id, db)
    indicadores = (
        db.query(Indicador)
        .filter(Indicador.proyecto_id == proyecto_id)
        .order_by(Indicador.created_at)
        .all()
    )
    return [_to_response(i) for i in indicadores]


# ── POST /proyectos/{id}/indicadores/ ────────────────

@router.post(
    "/{proyecto_id}/indicadores/",
    response_model=IndicadorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un indicador para el proyecto",
)
def crear_indicador(
    proyecto_id: str,
    payload: IndicadorCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _check_proyecto(proyecto_id, db)

    indicador = Indicador(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        nombre=payload.nombre,
        formula=payload.formula,
        valor_meta=payload.valor_meta,
        valor_real=payload.valor_real,
    )
    db.add(indicador)
    db.commit()
    db.refresh(indicador)
    logger.info(f"Indicador creado: id={indicador.id}, proyecto={proyecto_id}")
    return _to_response(indicador)


# ── PUT /proyectos/{id}/indicadores/{ind_id} ─────────

@router.put(
    "/{proyecto_id}/indicadores/{indicador_id}",
    response_model=IndicadorResponse,
    summary="Actualizar valores de un indicador",
)
def actualizar_indicador(
    proyecto_id: str,
    indicador_id: str,
    payload: IndicadorUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _check_proyecto(proyecto_id, db)
    indicador = _get_indicador(indicador_id, proyecto_id, db)

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(indicador, field, value)

    db.commit()
    db.refresh(indicador)
    logger.info(f"Indicador actualizado: id={indicador_id}")
    return _to_response(indicador)


# ── DELETE /proyectos/{id}/indicadores/{ind_id} ──────

@router.delete(
    "/{proyecto_id}/indicadores/{indicador_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un indicador",
)
def eliminar_indicador(
    proyecto_id: str,
    indicador_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _check_proyecto(proyecto_id, db)
    indicador = _get_indicador(indicador_id, proyecto_id, db)
    db.delete(indicador)
    db.commit()
    logger.info(f"Indicador eliminado: id={indicador_id}")


# ── Helpers ───────────────────────────────────────────

def _check_proyecto(proyecto_id: str, db: Session) -> Proyecto:
    p = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")
    return p


def _get_indicador(indicador_id: str, proyecto_id: str, db: Session) -> Indicador:
    i = db.query(Indicador).filter(
        Indicador.id == indicador_id,
        Indicador.proyecto_id == proyecto_id,
    ).first()
    if not i:
        raise HTTPException(status_code=404, detail=f"Indicador '{indicador_id}' no encontrado")
    return i


def _to_response(i: Indicador) -> IndicadorResponse:
    porcentaje = None
    if i.valor_meta and i.valor_meta > 0 and i.valor_real is not None:
        porcentaje = round(min((i.valor_real / i.valor_meta) * 100, 100), 2)
    return IndicadorResponse(
        id=i.id,
        proyecto_id=i.proyecto_id,
        nombre=i.nombre,
        formula=i.formula,
        valor_meta=i.valor_meta,
        valor_real=i.valor_real,
        porcentaje_avance=porcentaje,
        fecha_medicion=i.fecha_medicion,
        created_at=i.created_at,
    )
