"""
db_models.py — Modelos ORM de SQLAlchemy para persistencia de Vigía.

Mapeo objeto-relacional para las 4 capas de Vigía.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    ForeignKey, JSON, Text
)
from sqlalchemy.orm import relationship
from app.database import Base


class Proyecto(Base):
    """
    Entidad principal: un nodo de la red (proyecto social, iniciativa, etc.).
    """
    __tablename__ = "proyectos"

    id = Column(String(36), primary_key=True)  # UUID
    nombre = Column(String(120), nullable=False)
    descripcion = Column(Text, default="")
    responsable = Column(String(100), default="")
    fecha_inicio = Column(Date, nullable=True)
    estado = Column(String(20), default="ACTIVO")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relaciones
    indicadores = relationship("Indicador", back_populates="proyecto", cascade="all, delete-orphan")
    afirmaciones = relationship("Afirmacion", back_populates="proyecto", cascade="all, delete-orphan")
    datasets = relationship("Dataset", back_populates="proyecto", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Proyecto(id={self.id}, nombre={self.nombre!r})>"


class Indicador(Base):
    """
    Indicador de desempeño asociado a un Proyecto.
    (Ej: entregables_hechos, beneficiarios_reales, etc.)
    """
    __tablename__ = "indicadores"

    id = Column(String(36), primary_key=True)
    proyecto_id = Column(String(36), ForeignKey("proyectos.id"), nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    formula = Column(String(200), default="")
    valor_meta = Column(Float, nullable=True)
    valor_real = Column(Float, nullable=True)
    fecha_medicion = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relación inversa
    proyecto = relationship("Proyecto", back_populates="indicadores")

    def __repr__(self):
        return f"<Indicador(nombre={self.nombre!r}, valor_real={self.valor_real})>"


class Afirmacion(Base):
    """
    Afirmación de impacto a ser contrastada por el Agente 01.
    """
    __tablename__ = "afirmaciones"

    id = Column(String(36), primary_key=True)
    proyecto_id = Column(String(36), ForeignKey("proyectos.id"), nullable=False, index=True)
    texto = Column(Text, nullable=False)
    veredicto = Column(String(50), nullable=True)  # SUSTENTADA, REFUTADA, SIN DATOS
    fuente_url = Column(String(500), nullable=True)
    confianza = Column(Float, nullable=True)       # Score 0 a 1
    agente_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relación inversa
    proyecto = relationship("Proyecto", back_populates="afirmaciones")

    def __repr__(self):
        return f"<Afirmacion(veredicto={self.veredicto!r})>"


class Dataset(Base):
    """
    Dataset subido para el módulo Estadística -> ML (Agente 04).
    """
    __tablename__ = "datasets"

    id = Column(String(36), primary_key=True)
    proyecto_id = Column(String(36), ForeignKey("proyectos.id"), nullable=True, index=True)
    nombre = Column(String(120), nullable=False)
    descripcion = Column(Text, default="")
    s3_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relación inversa
    proyecto = relationship("Proyecto", back_populates="datasets")

    def __repr__(self):
        return f"<Dataset(nombre={self.nombre!r})>"


class AlertaLog(Base):
    """
    Registro de alertas y anomalías detectadas por el Agente 02.
    """
    __tablename__ = "alertas_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    proyecto_id = Column(String(36), ForeignKey("proyectos.id"), nullable=False, index=True)
    tipo_alerta = Column(String(50), nullable=False) # ej: IMPACTO_BAJO, ANOMALIA_ESTADISTICA
    mensaje = Column(Text, nullable=False)
    severidad = Column(String(20), default="MEDIA")
    
    def __repr__(self):
        return f"<AlertaLog(tipo={self.tipo_alerta}, severidad={self.severidad})>"
