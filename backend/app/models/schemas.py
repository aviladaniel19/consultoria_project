"""
schemas.py — Modelos Pydantic de Request/Response para Vigía.
Valida entradas y define exactamente qué retorna cada endpoint.
"""

from __future__ import annotations
from datetime import date, datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# ═══════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════

class TokenResponse(BaseModel):
    """Respuesta JWT al autenticarse."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Segundos hasta expiración")


class LoginRequest(BaseModel):
    """Credenciales de acceso."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


# ═══════════════════════════════════════════════════════
# PROYECTOS
# ═══════════════════════════════════════════════════════

class ProyectoCreate(BaseModel):
    """Payload para crear un nuevo proyecto."""
    nombre: str = Field(..., min_length=3, max_length=120, description="Nombre del proyecto")
    descripcion: str = Field(default="", max_length=1000)
    responsable: str = Field(default="", max_length=100)
    fecha_inicio: Optional[date] = Field(None, description="Fecha de inicio (YYYY-MM-DD)")
    estado: str = Field(default="ACTIVO", pattern="^(ACTIVO|PAUSADO|CERRADO)$")

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("El nombre no puede estar vacío")
        return v.strip()


class ProyectoUpdate(BaseModel):
    """Payload para actualizar un proyecto (todos los campos son opcionales)."""
    nombre: Optional[str] = Field(None, min_length=3, max_length=120)
    descripcion: Optional[str] = Field(None, max_length=1000)
    responsable: Optional[str] = Field(None, max_length=100)
    fecha_inicio: Optional[date] = None
    estado: Optional[str] = Field(None, pattern="^(ACTIVO|PAUSADO|CERRADO)$")


class ProyectoResponse(BaseModel):
    """Representación de un proyecto en respuestas."""
    id: str
    nombre: str
    descripcion: str
    responsable: str
    fecha_inicio: Optional[date]
    estado: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProyectoListResponse(BaseModel):
    """Respuesta paginada de proyectos."""
    total: int
    proyectos: list[ProyectoResponse]


# ═══════════════════════════════════════════════════════
# INDICADORES
# ═══════════════════════════════════════════════════════

class IndicadorCreate(BaseModel):
    """Payload para crear un indicador."""
    nombre: str = Field(..., min_length=3, max_length=100)
    formula: str = Field(default="", max_length=200, description="Ej: (valor_real / valor_meta) * 100")
    valor_meta: Optional[float] = Field(None, ge=0)
    valor_real: Optional[float] = Field(None, ge=0)

    @field_validator("nombre")
    @classmethod
    def nombre_no_vacio(cls, v: str) -> str:
        return v.strip()


class IndicadorUpdate(BaseModel):
    """Actualización parcial de indicador."""
    nombre: Optional[str] = Field(None, min_length=3, max_length=100)
    formula: Optional[str] = Field(None, max_length=200)
    valor_meta: Optional[float] = Field(None, ge=0)
    valor_real: Optional[float] = Field(None, ge=0)


class IndicadorResponse(BaseModel):
    """Representación de un indicador."""
    id: str
    proyecto_id: str
    nombre: str
    formula: str
    valor_meta: Optional[float]
    valor_real: Optional[float]
    porcentaje_avance: Optional[float] = Field(None, description="(valor_real/valor_meta)*100")
    fecha_medicion: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class IndiceVigiaResponse(BaseModel):
    """Los 4 índices compuestos de Vigía para un proyecto."""
    proyecto_id: str
    indice_avance: Optional[float] = Field(None, description="% de cumplimiento promedio de indicadores")
    indice_impacto: Optional[float] = Field(None, description="Relación beneficiarios reales vs esperados")
    indice_capacidad: Optional[float] = Field(None, description="Indicadores con valor_real > 0 / total")
    indice_veracidad: Optional[float] = Field(None, description="Afirmaciones SUSTENTADAS / total contrastadas")


# ═══════════════════════════════════════════════════════
# AFIRMACIONES
# ═══════════════════════════════════════════════════════

class AfirmacionCreate(BaseModel):
    """Payload para registrar una afirmación a contrastar."""
    texto: str = Field(..., min_length=10, max_length=2000, description="La afirmación de impacto")

    @field_validator("texto")
    @classmethod
    def texto_no_vacio(cls, v: str) -> str:
        return v.strip()


class AfirmacionResponse(BaseModel):
    """Representación de una afirmación."""
    id: str
    proyecto_id: str
    texto: str
    veredicto: Optional[str] = Field(None, description="SUSTENTADA | REFUTADA | SIN DATOS")
    fuente_url: Optional[str]
    confianza: Optional[float] = Field(None, ge=0, le=1)
    agente_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class AfirmacionListResponse(BaseModel):
    total: int
    afirmaciones: list[AfirmacionResponse]


# ═══════════════════════════════════════════════════════
# DATASETS
# ═══════════════════════════════════════════════════════

class DatasetResponse(BaseModel):
    """Representación de un dataset registrado."""
    id: str
    proyecto_id: Optional[str]
    nombre: str
    descripcion: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetAnalisisResponse(BaseModel):
    """Resultado del análisis estadístico de un dataset."""
    nombre: str
    n_filas: int
    n_columnas: int
    memoria_mb: float
    columnas: list[dict[str, Any]]
    datos_faltantes: list[dict[str, Any]]
    patron_missingness: str
    recomendaciones: list[str]


# ═══════════════════════════════════════════════════════
# ALERTAS
# ═══════════════════════════════════════════════════════

class AlertaResponse(BaseModel):
    """Representación de una alerta de Vigía."""
    id: int
    timestamp: datetime
    proyecto_id: str
    tipo_alerta: str
    mensaje: str
    severidad: str

    model_config = {"from_attributes": True}


class AlertaListResponse(BaseModel):
    total: int
    alertas: list[AlertaResponse]
