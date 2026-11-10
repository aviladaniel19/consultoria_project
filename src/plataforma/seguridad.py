"""Controles de seguridad compartidos por la web y la API.

- `url_no_permitida`: evita que una API conectada desde la web apunte a la red interna
  (SSRF): la base de datos, servicios del servidor o metadatos de la nube.
- `Limitador`: frena los intentos de adivinar claves, por dirección IP.
"""
from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from .config import get_settings


def url_no_permitida(url: str) -> str | None:
    """Motivo por el que no se permite consultar la URL, o None si se permite.

    Solo acepta http(s) hacia direcciones públicas. Con PLATAFORMA_PERMITIR_REDES_PRIVADAS=true
    (por ejemplo, para APIs internas de la universidad) acepta también redes privadas.
    """
    partes = urlsplit(url.strip())
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return "La dirección de la API debe empezar por http:// o https:// e incluir un servidor."
    if get_settings().permitir_redes_privadas:
        return None
    try:
        direcciones = {info[4][0] for info in socket.getaddrinfo(partes.hostname, partes.port or None)}
    except (socket.gaierror, UnicodeError):
        return f"No se encontró el servidor «{partes.hostname}»."
    for d in direcciones:
        ip = ipaddress.ip_address(d.split("%")[0])
        if not ip.is_global:
            return (f"«{partes.hostname}» apunta a una dirección interna ({ip}). Por seguridad solo se "
                    "conectan APIs públicas; para APIs internas, activa PLATAFORMA_PERMITIR_REDES_PRIVADAS.")
    return None


class Limitador:
    """Cuenta intentos fallidos por IP en una ventana deslizante. Vive en memoria: basta para un
    proceso; detrás de un proxy, uvicorn debe recibir la IP real (--proxy-headers)."""

    def __init__(self, maximo: int = 10, ventana_s: int = 15 * 60):
        self.maximo, self.ventana_s = maximo, ventana_s
        self._fallos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _vigentes(self, ip: str, ahora: float) -> deque[float]:
        fallos = self._fallos[ip]
        while fallos and ahora - fallos[0] > self.ventana_s:
            fallos.popleft()
        return fallos

    def bloqueado(self, ip: str) -> int:
        """Segundos que faltan para poder intentar de nuevo; 0 si no está bloqueado."""
        with self._lock:
            ahora = time.monotonic()
            fallos = self._vigentes(ip, ahora)
            if len(fallos) < self.maximo:
                return 0
            return max(1, int(self.ventana_s - (ahora - fallos[0])))

    def fallo(self, ip: str) -> None:
        with self._lock:
            self._vigentes(ip, time.monotonic()).append(time.monotonic())

    def exito(self, ip: str) -> None:
        with self._lock:
            self._fallos.pop(ip, None)

    def reiniciar(self) -> None:
        with self._lock:
            self._fallos.clear()


intentos_clave = Limitador()
