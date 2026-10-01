"""
dependencies.py — Inyección de dependencias con Depends() de FastAPI.
"""

import sys
import os
from functools import lru_cache
from fastapi import Depends

# Agrega el directorio raíz del proyecto al path para importar src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.config import get_settings, Settings


class VigiaService:
    """
    Servicio centralizado para lógica de Vigía.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        # Aquí se inicializarían los clientes como LangChain/Groq
        self._groq_client = None

    def get_groq(self):
        # TODO: inicializar cliente de Groq
        pass

def get_vigia_service(
    settings: Settings = Depends(get_settings)
) -> VigiaService:
    """
    Dependencia que provee el servicio base.
    """
    return VigiaService(settings)
