import socket

import pytest

from plataforma.config import get_settings
from plataforma.seguridad import Limitador, url_no_permitida


def _resuelve_a(monkeypatch, ip: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, "", (ip, 0))])


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.10", "172.17.0.2",
                                "169.254.169.254", "::1", "fd00::1"])
def test_rechaza_apis_en_la_red_interna(monkeypatch, ip):
    monkeypatch.setattr(get_settings(), "permitir_redes_privadas", False)
    _resuelve_a(monkeypatch, ip)
    assert "dirección interna" in url_no_permitida("http://servicio.interno/api")


def test_acepta_apis_publicas_y_redes_privadas_si_se_permiten(monkeypatch):
    monkeypatch.setattr(get_settings(), "permitir_redes_privadas", False)
    _resuelve_a(monkeypatch, "8.8.8.8")
    assert url_no_permitida("https://www.datos.gov.co/resource/gdxc-w37w.json") is None
    monkeypatch.setattr(get_settings(), "permitir_redes_privadas", True)
    _resuelve_a(monkeypatch, "10.0.0.5")
    assert url_no_permitida("http://api.usta.local/datos") is None


@pytest.mark.parametrize("url", ["ftp://servidor/x", "file:///etc/passwd", "http://", "servidor.com/api"])
def test_rechaza_esquemas_y_direcciones_mal_formadas(url):
    assert "http://" in url_no_permitida(url)


def test_limitador_bloquea_tras_varios_fallos_y_libera_al_acertar():
    lim = Limitador(maximo=3, ventana_s=60)
    for _ in range(3):
        assert lim.bloqueado("1.2.3.4") == 0
        lim.fallo("1.2.3.4")
    assert 0 < lim.bloqueado("1.2.3.4") <= 60
    assert lim.bloqueado("5.6.7.8") == 0                 # otra IP no se ve afectada
    lim.exito("1.2.3.4")
    assert lim.bloqueado("1.2.3.4") == 0


def test_limitador_olvida_fallos_viejos(monkeypatch):
    import plataforma.seguridad as s
    reloj = [1000.0]
    monkeypatch.setattr(s.time, "monotonic", lambda: reloj[0])
    lim = Limitador(maximo=2, ventana_s=60)
    lim.fallo("ip")
    lim.fallo("ip")
    assert lim.bloqueado("ip") > 0
    reloj[0] += 61
    assert lim.bloqueado("ip") == 0
