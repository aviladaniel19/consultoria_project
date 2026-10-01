"""
services/__init__.py — Re-exporta el servicio principal.

Los módulos individuales (api_client, returns, indicators, etc.)
ahora viven dentro de backend/app/services/ en lugar de src/.
Esto elimina los hacks de sys.path y mantiene todo el código
dentro del paquete app.
"""

try:
    from app.services.risk_service import RiskService  # noqa: F401
    __all__ = ["RiskService"]
except ImportError:
    # RiskService depende de yfinance y otras libs del módulo financiero.
    # Si no están instaladas (entorno Vigía puro), se omite sin error.
    __all__ = []
