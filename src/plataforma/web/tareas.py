"""Cargas lanzadas desde la web, en un hilo aparte para no bloquear la página.

Cada fuente admite una sola carga a la vez. El resultado queda en meta.runs (como cualquier
carga) y además en memoria, para que la página de progreso muestre lo que pasó.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..config import get_settings
from ..ingestion.engine import RunResult, run_source
from ..registry.loader import RegistryError, load_file
from ..storage.db import bootstrap, get_engine

log = logging.getLogger(__name__)


@dataclass
class Tarea:
    fuente: str
    inicio: float = field(default_factory=time.time)
    fin: float | None = None
    resultado: RunResult | None = None
    error: str | None = None          # error antes de empezar la carga (YAML inválido, etc.)

    @property
    def activa(self) -> bool:
        return self.fin is None

    @property
    def segundos(self) -> int:
        return int((self.fin or time.time()) - self.inicio)


_tareas: dict[str, Tarea] = {}
_candado = threading.Lock()


def _ejecutar(tarea: Tarea) -> None:
    try:
        spec = load_file(get_settings().sources_dir / f"{tarea.fuente}.yml")
        engine = get_engine()
        bootstrap(engine)
        tarea.resultado = run_source(engine, spec)
    except RegistryError as e:
        tarea.error = str(e)
    except Exception as e:  # noqa: BLE001 — se muestra en la página de progreso
        log.exception("falló la carga de %s", tarea.fuente)
        tarea.error = f"{type(e).__name__}: {e}"
    finally:
        tarea.fin = time.time()


def lanzar(fuente: str) -> bool:
    """Inicia la carga en segundo plano. Devuelve False si ya hay una en curso para esa fuente."""
    with _candado:
        actual = _tareas.get(fuente)
        if actual and actual.activa:
            return False
        tarea = _tareas[fuente] = Tarea(fuente)
    threading.Thread(target=_ejecutar, args=(tarea,), name=f"carga-{fuente}", daemon=True).start()
    return True


def estado(fuente: str) -> Tarea | None:
    return _tareas.get(fuente)


def en_curso() -> list[str]:
    return [f for f, t in _tareas.items() if t.activa]


def esperar(fuente: str, segundos: float = 60) -> Tarea | None:
    """Para pruebas y scripts: espera a que termine la carga de una fuente."""
    limite = time.time() + segundos
    while (t := _tareas.get(fuente)) and t.activa and time.time() < limite:
        time.sleep(0.1)
    return _tareas.get(fuente)


def resumen(t: Tarea) -> dict[str, Any]:
    r = t.resultado
    return {"fuente": t.fuente, "activa": t.activa, "segundos": t.segundos, "error": t.error or (r.error if r else None),
            "estado": r.status if r else None, "cargados": r.loaded if r else None,
            "extraidos": r.extracted if r else None, "publicada": r.published if r else None,
            "filas_publicadas": r.published_rows if r else None,
            "error_publicacion": r.publish_error if r else None,
            "reglas": r.failed_checks if r else []}
