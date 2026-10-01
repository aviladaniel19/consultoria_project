"""
seed.py — Carga datos iniciales de demostración en la BD de Vigía.

Ejecutar una sola vez:
    python seed.py

Crea:
  - 3 proyectos demo con indicadores y afirmaciones de prueba
  - No modifica datos si los proyectos ya existen
"""

import sys
import os
from pathlib import Path
from datetime import date

# Agregar backend/ al path
sys.path.insert(0, str(Path(__file__).parent))

from app.config import get_settings
from app.database import engine, Base, SessionLocal
from app.models.db_models import Proyecto, Indicador, Afirmacion, Dataset

settings = get_settings()


PROYECTOS_DEMO = [
    {
        "id": "p-demo-001",
        "nombre": "Fundación Vigía — Nutrición Infantil",
        "descripcion": "Programa de intervención nutricional en comunidades de la Localidad de Suba.",
        "responsable": "Dra. Carmen Lucía Vargas",
        "fecha_inicio": date(2025, 1, 15),
        "estado": "ACTIVO",
        "indicadores": [
            {
                "id": "i-001-01",
                "nombre": "Niños beneficiarios",
                "formula": "(beneficiarios_reales / beneficiarios_meta) * 100",
                "valor_meta": 500.0,
                "valor_real": 312.0,
            },
            {
                "id": "i-001-02",
                "nombre": "Talleres nutricionales realizados",
                "formula": "(talleres_realizados / talleres_programados) * 100",
                "valor_meta": 24.0,
                "valor_real": 18.0,
            },
            {
                "id": "i-001-03",
                "nombre": "Reducción de desnutrición (%)",
                "formula": "diferencia_porcentual_desnutricion",
                "valor_meta": 15.0,
                "valor_real": 8.5,
            },
        ],
        "afirmaciones": [
            {
                "id": "a-001-01",
                "texto": "El programa redujo la desnutrición infantil en un 15% en la zona de intervención.",
                "veredicto": None,
            },
            {
                "id": "a-001-02",
                "texto": "Las intervenciones nutricionales tienen mayor eficacia cuando se combinan con educación parental.",
                "veredicto": None,
            },
        ],
    },
    {
        "id": "p-demo-002",
        "nombre": "Proyecto USTA — Calidad del Aire Bogotá",
        "descripcion": "Monitoreo estadístico de calidad del aire en zonas de alta contaminación.",
        "responsable": "Ing. Felipe Mora",
        "fecha_inicio": date(2025, 3, 1),
        "estado": "ACTIVO",
        "indicadores": [
            {
                "id": "i-002-01",
                "nombre": "Estaciones de monitoreo activas",
                "formula": "(estaciones_activas / estaciones_instaladas) * 100",
                "valor_meta": 10.0,
                "valor_real": 7.0,
            },
            {
                "id": "i-002-02",
                "nombre": "Días con PM2.5 menor a 25 μg/m³",
                "formula": "(dias_cumplimiento / dias_totales) * 100",
                "valor_meta": 200.0,
                "valor_real": 143.0,
            },
        ],
        "afirmaciones": [
            {
                "id": "a-002-01",
                "texto": "La concentración de PM2.5 en Bogotá supera el límite OMS de 15 μg/m³ más del 60% de los días.",
                "veredicto": None,
            },
        ],
    },
    {
        "id": "p-demo-003",
        "nombre": "Retail Store — Análisis de Ventas",
        "descripcion": "Dataset de prueba del módulo Estadística → ML. Basado en retail_store_sales.",
        "responsable": "Equipo Vigía",
        "fecha_inicio": date(2025, 6, 1),
        "estado": "ACTIVO",
        "indicadores": [
            {
                "id": "i-003-01",
                "nombre": "Registros procesados",
                "formula": "filas_limpias / filas_originales * 100",
                "valor_meta": 5000.0,
                "valor_real": None,
            },
        ],
        "afirmaciones": [],
    },
]


def main():
    print("=" * 60)
    print("VIGÍA — Cargando datos de demostración")
    print("=" * 60)

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        for p_data in PROYECTOS_DEMO:
            existente = db.query(Proyecto).filter(Proyecto.id == p_data["id"]).first()
            if existente:
                print(f"  ⚡ Proyecto ya existe: '{p_data['nombre']}' — omitido")
                continue

            proyecto = Proyecto(
                id=p_data["id"],
                nombre=p_data["nombre"],
                descripcion=p_data["descripcion"],
                responsable=p_data["responsable"],
                fecha_inicio=p_data["fecha_inicio"],
                estado=p_data["estado"],
            )
            db.add(proyecto)

            for ind in p_data.get("indicadores", []):
                indicador = Indicador(
                    id=ind["id"],
                    proyecto_id=p_data["id"],
                    nombre=ind["nombre"],
                    formula=ind["formula"],
                    valor_meta=ind["valor_meta"],
                    valor_real=ind["valor_real"],
                )
                db.add(indicador)

            for afirm in p_data.get("afirmaciones", []):
                afirmacion = Afirmacion(
                    id=afirm["id"],
                    proyecto_id=p_data["id"],
                    texto=afirm["texto"],
                    veredicto=afirm.get("veredicto"),
                )
                db.add(afirmacion)

            db.commit()
            print(f"  ✅ Proyecto creado: '{p_data['nombre']}'")

        print("\n✅ Seed completado")
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error durante seed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
