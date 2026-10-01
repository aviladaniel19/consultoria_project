"""
afirmaciones.py — CRUD + Contraste de Afirmaciones de Impacto.

Endpoints:
  GET    /proyectos/{id}/afirmaciones/                              → listar afirmaciones
  POST   /proyectos/{id}/afirmaciones/                              → registrar afirmación
  DELETE /proyectos/{id}/afirmaciones/{afirmacion_id}               → eliminar afirmación
  POST   /proyectos/{id}/afirmaciones/{afirmacion_id}/contrastar    → Agente 01 (individual)
  POST   /proyectos/{id}/afirmaciones/contrastar-todas              → Agente 01 (batch)
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.db_models import AlertaLog, Proyecto, Afirmacion
from app.models.schemas import (
    AfirmacionCreate, AfirmacionResponse, AfirmacionListResponse,
)
from app.routers.auth import get_current_user

router = APIRouter(prefix="/proyectos", tags=["Afirmaciones"])
logger = logging.getLogger("vigia.afirmaciones")


# ════════════════════════════════════════════════════════════
# SCHEMAS LOCALES (solo para este router)
# ════════════════════════════════════════════════════════════

class ContrasteResponse(BaseModel):
    """Resultado del Agente 01 para una afirmación contrastada."""
    afirmacion_id: str
    texto: str
    veredicto: str = Field(..., description="SUSTENTADA | REFUTADA | SIN DATOS")
    razonamiento: str
    fuente_url: Optional[str] = None
    confianza: float = Field(..., ge=0.0, le=1.0)
    indicadores_clave: list[str] = []
    proveedor: str = Field(..., description="gemini | groq | offline")


class BatchContrasteResponse(BaseModel):
    """Resultado del contraste en batch para todas las afirmaciones pendientes."""
    proyecto_id: str
    total_procesadas: int
    sustentadas: int
    refutadas: int
    sin_datos: int
    resultados: list[ContrasteResponse]


# ════════════════════════════════════════════════════════════
# GET /proyectos/{id}/afirmaciones/
# ════════════════════════════════════════════════════════════

@router.get(
    "/{proyecto_id}/afirmaciones/",
    response_model=AfirmacionListResponse,
    summary="Listar afirmaciones del proyecto",
)
def listar_afirmaciones(
    proyecto_id: str,
    db: Session = Depends(get_db),
):
    _check_proyecto(proyecto_id, db)
    afirmaciones = (
        db.query(Afirmacion)
        .filter(Afirmacion.proyecto_id == proyecto_id)
        .order_by(Afirmacion.created_at.desc())
        .all()
    )
    return AfirmacionListResponse(total=len(afirmaciones), afirmaciones=afirmaciones)


# ════════════════════════════════════════════════════════════
# POST /proyectos/{id}/afirmaciones/
# ════════════════════════════════════════════════════════════

@router.post(
    "/{proyecto_id}/afirmaciones/",
    response_model=AfirmacionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una afirmación para contrastar",
)
def crear_afirmacion(
    proyecto_id: str,
    payload: AfirmacionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _check_proyecto(proyecto_id, db)

    afirmacion = Afirmacion(
        id=str(uuid.uuid4()),
        proyecto_id=proyecto_id,
        texto=payload.texto,
        veredicto=None,
        fuente_url=None,
        confianza=None,
        agente_id=None,
    )
    db.add(afirmacion)
    db.commit()
    db.refresh(afirmacion)
    logger.info(f"Afirmación registrada: id={afirmacion.id}")
    return afirmacion


# ════════════════════════════════════════════════════════════
# DELETE /proyectos/{id}/afirmaciones/{afirmacion_id}
# ════════════════════════════════════════════════════════════

@router.delete(
    "/{proyecto_id}/afirmaciones/{afirmacion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una afirmación",
)
def eliminar_afirmacion(
    proyecto_id: str,
    afirmacion_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    _check_proyecto(proyecto_id, db)
    afirmacion = db.query(Afirmacion).filter(
        Afirmacion.id == afirmacion_id,
        Afirmacion.proyecto_id == proyecto_id,
    ).first()
    if not afirmacion:
        raise HTTPException(status_code=404, detail=f"Afirmación '{afirmacion_id}' no encontrada")
    db.delete(afirmacion)
    db.commit()
    logger.info(f"Afirmación eliminada: id={afirmacion_id}")


# ════════════════════════════════════════════════════════════
# POST /proyectos/{id}/afirmaciones/{afirmacion_id}/contrastar
# Agente 01 — análisis individual
# ════════════════════════════════════════════════════════════

@router.post(
    "/{proyecto_id}/afirmaciones/{afirmacion_id}/contrastar",
    response_model=ContrasteResponse,
    summary="🤖 Agente 01: Contrastar una afirmación de impacto",
    description=(
        "Invoca el Agente 01 de Vigía para contrastar una afirmación de impacto "
        "usando inteligencia artificial (Gemini → Groq → modo offline). "
        "Actualiza el veredicto, fuente y confianza en base de datos y genera "
        "una alerta si la confianza es baja o el veredicto es REFUTADA."
    ),
)
async def contrastar_afirmacion_individual(
    proyecto_id: str,
    afirmacion_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from app.services.agente_01 import contrastar_afirmacion

    _check_proyecto(proyecto_id, db)
    afirmacion = _get_afirmacion(afirmacion_id, proyecto_id, db)

    logger.info(f"[Agente 01] Contrastando afirmacion_id={afirmacion_id}")

    try:
        resultado = await contrastar_afirmacion(afirmacion.texto)
    except Exception as e:
        logger.error(f"[Agente 01] Error inesperado: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"El Agente 01 no pudo procesar la afirmación: {str(e)}",
        )

    # Persistir resultado en DB
    afirmacion.veredicto = resultado["veredicto"]
    afirmacion.fuente_url = resultado.get("fuente_url")
    afirmacion.confianza = resultado["confianza"]
    afirmacion.agente_id = f"agente-01-{resultado.get('proveedor', 'offline')}"
    db.commit()
    db.refresh(afirmacion)

    # Generar alerta si veredicto es REFUTADA o confianza muy baja
    _generar_alerta_si_aplica(proyecto_id, afirmacion, resultado, db)

    logger.info(
        f"[Agente 01] Resultado: {resultado['veredicto']} "
        f"(confianza={resultado['confianza']}, proveedor={resultado.get('proveedor')})"
    )

    return ContrasteResponse(
        afirmacion_id=afirmacion.id,
        texto=afirmacion.texto,
        **resultado,
    )


# ════════════════════════════════════════════════════════════
# POST /proyectos/{id}/afirmaciones/contrastar-todas
# Agente 01 — batch (solo afirmaciones pendientes)
# ════════════════════════════════════════════════════════════

@router.post(
    "/{proyecto_id}/afirmaciones/contrastar-todas",
    response_model=BatchContrasteResponse,
    summary="🤖 Agente 01: Contrastar todas las afirmaciones pendientes",
    description=(
        "Invoca el Agente 01 para todas las afirmaciones sin veredicto del proyecto. "
        "Procesa secuencialmente para respetar rate limits de las APIs."
    ),
)
async def contrastar_todas(
    proyecto_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import asyncio
    from app.services.agente_01 import contrastar_afirmacion

    _check_proyecto(proyecto_id, db)

    # Solo las pendientes (sin veredicto)
    pendientes = (
        db.query(Afirmacion)
        .filter(
            Afirmacion.proyecto_id == proyecto_id,
            Afirmacion.veredicto.is_(None),
        )
        .order_by(Afirmacion.created_at)
        .all()
    )

    if not pendientes:
        logger.info(f"[Agente 01 Batch] No hay afirmaciones pendientes en proyecto={proyecto_id}")
        return BatchContrasteResponse(
            proyecto_id=proyecto_id,
            total_procesadas=0,
            sustentadas=0,
            refutadas=0,
            sin_datos=0,
            resultados=[],
        )

    logger.info(f"[Agente 01 Batch] Procesando {len(pendientes)} afirmaciones en proyecto={proyecto_id}")

    resultados = []
    sustentadas = refutadas = sin_datos = 0

    for afirmacion in pendientes:
        try:
            resultado = await contrastar_afirmacion(afirmacion.texto)

            # Persistir
            afirmacion.veredicto = resultado["veredicto"]
            afirmacion.fuente_url = resultado.get("fuente_url")
            afirmacion.confianza = resultado["confianza"]
            afirmacion.agente_id = f"agente-01-{resultado.get('proveedor', 'offline')}"
            db.commit()
            db.refresh(afirmacion)

            # Generar alerta si aplica
            _generar_alerta_si_aplica(proyecto_id, afirmacion, resultado, db)

            # Contadores
            v = resultado["veredicto"]
            if v == "SUSTENTADA":
                sustentadas += 1
            elif v == "REFUTADA":
                refutadas += 1
            else:
                sin_datos += 1

            resultados.append(ContrasteResponse(
                afirmacion_id=afirmacion.id,
                texto=afirmacion.texto,
                **resultado,
            ))

            # Pequeña pausa entre llamadas al LLM (evitar rate limit)
            if len(pendientes) > 1:
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"[Agente 01 Batch] Error en afirmacion_id={afirmacion.id}: {e}")
            sin_datos += 1
            resultados.append(ContrasteResponse(
                afirmacion_id=afirmacion.id,
                texto=afirmacion.texto,
                veredicto="SIN DATOS",
                razonamiento=f"Error durante el análisis: {str(e)[:200]}",
                fuente_url=None,
                confianza=0.0,
                indicadores_clave=[],
                proveedor="error",
            ))

    logger.info(
        f"[Agente 01 Batch] Completado: {sustentadas} sustentadas, "
        f"{refutadas} refutadas, {sin_datos} sin datos"
    )

    return BatchContrasteResponse(
        proyecto_id=proyecto_id,
        total_procesadas=len(pendientes),
        sustentadas=sustentadas,
        refutadas=refutadas,
        sin_datos=sin_datos,
        resultados=resultados,
    )


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def _check_proyecto(proyecto_id: str, db: Session) -> Proyecto:
    p = db.query(Proyecto).filter(Proyecto.id == proyecto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Proyecto '{proyecto_id}' no encontrado")
    return p


def _get_afirmacion(afirmacion_id: str, proyecto_id: str, db: Session) -> Afirmacion:
    a = db.query(Afirmacion).filter(
        Afirmacion.id == afirmacion_id,
        Afirmacion.proyecto_id == proyecto_id,
    ).first()
    if not a:
        raise HTTPException(
            status_code=404,
            detail=f"Afirmación '{afirmacion_id}' no encontrada en proyecto '{proyecto_id}'",
        )
    return a


def _generar_alerta_si_aplica(
    proyecto_id: str,
    afirmacion: Afirmacion,
    resultado: dict,
    db: Session,
) -> None:
    """
    Registra una alerta en AlertaLog si:
    - El veredicto es REFUTADA (severidad ALTA)
    - La confianza es < 0.4 (severidad MEDIA)
    """
    veredicto = resultado.get("veredicto", "SIN DATOS")
    confianza = resultado.get("confianza", 0.5)

    if veredicto == "REFUTADA":
        alerta = AlertaLog(
            proyecto_id=proyecto_id,
            tipo_alerta="AFIRMACION_REFUTADA",
            mensaje=(
                f"El Agente 01 refutó la afirmación: "
                f"\"{afirmacion.texto[:120]}...\" "
                f"(confianza={confianza:.0%}). "
                f"Razonamiento: {resultado.get('razonamiento', '')[:200]}"
            ),
            severidad="ALTA",
        )
        db.add(alerta)
        db.commit()
        logger.warning(f"[Alerta ALTA] Afirmación refutada: id={afirmacion.id}")

    elif confianza < 0.4 and veredicto == "SIN DATOS":
        alerta = AlertaLog(
            proyecto_id=proyecto_id,
            tipo_alerta="VERACIDAD_BAJA",
            mensaje=(
                f"Afirmación sin evidencia suficiente: "
                f"\"{afirmacion.texto[:120]}...\" "
                f"(confianza={confianza:.0%}). "
                f"Se recomienda aportar fuentes o datos cuantitativos."
            ),
            severidad="MEDIA",
        )
        db.add(alerta)
        db.commit()
        logger.info(f"[Alerta MEDIA] Veracidad baja: id={afirmacion.id}")
