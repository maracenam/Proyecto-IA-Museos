"""Pruebas del listado (fixtures reales) y del cliente HTTP (transporte simulado)."""

import httpx
import pytest

from pipeline.extract.cliente import ClienteSurdoc, ErrorDescarga, RutaProhibida
from pipeline.extract.listado import listar_ids, parsear_listado
from tests.conftest import leer_fixture

ROBOTS = "User-agent: *\nDisallow: /registro/*/pdf\nDisallow: /search/\n"


class RelojFalso:
    def __init__(self):
        self.ahora = 0.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.ahora

    def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.ahora += segundos


def cliente_con(manejador, reloj=None, **kwargs) -> ClienteSurdoc:
    reloj = reloj or RelojFalso()

    def enrutar(peticion: httpx.Request) -> httpx.Response:
        if peticion.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return manejador(peticion)

    return ClienteSurdoc(
        "https://www.surdoc.cl", "ObservatorioPruebas/0.1 (+contacto)",
        transport=httpx.MockTransport(enrutar), dormir=reloj.dormir, reloj=reloj, **kwargs,
    )  # fmt: skip


# --- Listado ---


def test_parsear_listado_real():
    p0 = parsear_listado(leer_fixture("listado_548_16_p0.html"), 16)
    p3 = parsear_listado(leer_fixture("listado_548_16_p3.html"), 16)
    assert p0.total == 77 and len(p0.ids) == 21 and p0.ids[0] == "16-1002"
    assert len(p3.ids) == 14 and p3.ids[-1] == "16-999"  # incluye 16-972, sin título
    assert not set(p0.ids) & set(p3.ids)


def test_listar_recorre_paginas_hasta_una_vacia():
    paginas = {"0": "listado_548_16_p0.html", "1": "listado_548_16_p3.html"}
    vistos = []

    def manejador(peticion):
        pagina = peticion.url.params["page"]
        vistos.append(dict(peticion.url.params))
        if pagina in paginas:
            return httpx.Response(200, text=leer_fixture(paginas[pagina]))
        return httpx.Response(200, text="<html><body>0 registros</body></html>")

    listado = listar_ids(cliente_con(manejador), 16, 548)
    assert len(listado.ids) == 35 and listado.paginas == 2
    assert listado.total_informado == 77 and not listado.completo
    assert vistos[0] == {
        "f[0]": "institution:16",
        "first_level_classification": "548",
        "query": "",
        "page": "0",
    }


# --- Cliente ---


def test_user_agent_y_pausa_minima_de_2_segundos():
    reloj = RelojFalso()
    agentes = []

    def manejador(peticion):
        agentes.append(peticion.headers["User-Agent"])
        return httpx.Response(200, text="ok")

    cliente = cliente_con(manejador, reloj, pausa_segundos=0.1)  # se fuerza a 2 s
    for _ in range(3):
        cliente.obtener("/colecciones")
    assert agentes == ["ObservatorioPruebas/0.1 (+contacto)"] * 3
    assert cliente.pausa == 2.0
    assert reloj.esperas and all(e >= 2.0 for e in reloj.esperas)


def test_reintenta_con_espera_creciente_y_respeta_retry_after():
    respuestas = iter([
        httpx.Response(503), httpx.Response(429, headers={"Retry-After": "30"}),
        httpx.Response(200, text="<html>ficha</html>"),
    ])  # fmt: skip
    reloj = RelojFalso()
    cliente = cliente_con(lambda _: next(respuestas), reloj)
    assert cliente.obtener("/registro/16-1") == "<html>ficha</html>"
    assert 30.0 in reloj.esperas  # Retry-After manda sobre la espera exponencial (4 s)
    assert cliente.solicitudes == 4  # robots.txt + 3 intentos


def test_se_rinde_tras_los_reintentos():
    cliente = cliente_con(lambda _: httpx.Response(502), reintentos=2)
    with pytest.raises(ErrorDescarga, match="tras 3 intentos"):
        cliente.obtener("/registro/16-1")


def test_404_no_se_reintenta():
    llamadas = []

    def manejador(peticion):
        llamadas.append(1)
        return httpx.Response(404)

    with pytest.raises(ErrorDescarga) as error:
        cliente_con(manejador).obtener("/registro/16-1")
    assert error.value.estado == 404 and len(llamadas) == 1


def test_respeta_robots_txt():
    cliente = cliente_con(lambda _: httpx.Response(200, text="pdf"))
    with pytest.raises(RutaProhibida):
        cliente.obtener("/registro/16-1/pdf")
    assert cliente.permitido("/registro/16-1")


# --- robots.txt real de SURDOC (comodines) ---


@pytest.mark.parametrize(
    ("ruta", "permitido"),
    [
        ("/colecciones", True),
        ("/registro/16-447", True),
        ("/registro/16-447/pdf", False),
        ("/registro-descarga/16-447/objectid", False),
        ("/search/algo", False),
        ("/core/misc/estilo.css", True),  # Allow más específico que Disallow: /core/
        ("/core/lib/archivo.php", False),
    ],
)
def test_robots_real_de_surdoc(ruta, permitido):
    from pipeline.extract.robots import Robots

    robots = Robots(leer_fixture("robots_surdoc.txt"))
    assert robots.permitido("ObservatorioSURDOC/0.1", ruta) is permitido


def test_listado_incluye_ficha_sin_titulo():
    # 16-972 no tiene "Objeto": su tarjeta no trae a.record-title, solo el enlace "Ver".
    assert "16-972" in parsear_listado(leer_fixture("listado_548_16_p3.html"), 16).ids
