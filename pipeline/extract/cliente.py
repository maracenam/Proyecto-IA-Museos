"""Cliente HTTP para SURDOC que respeta la fuente (RNF-01):
máximo 1 solicitud cada 2 segundos, User-Agent identificable, robots.txt y
reintentos con espera creciente ante errores de red, 429 y 5xx."""

import logging
import time
from collections.abc import Callable

import httpx

from pipeline.config import PAUSA_MINIMA_SEGUNDOS
from pipeline.extract.robots import Robots

log = logging.getLogger(__name__)

ESTADOS_REINTENTABLES = {429, 500, 502, 503, 504}


class ErrorDescarga(Exception):
    """La página no se pudo descargar tras los reintentos, o la respuesta no es reintentable."""

    def __init__(self, mensaje: str, estado: int | None = None):
        super().__init__(mensaje)
        self.estado = estado


class RutaProhibida(Exception):
    """robots.txt no permite la ruta pedida."""


class ClienteSurdoc:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        pausa_segundos: float = PAUSA_MINIMA_SEGUNDOS,
        reintentos: int = 4,
        espera_base_segundos: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
    ):
        if not user_agent.strip():
            raise ValueError("El User-Agent debe identificar el proyecto y un contacto.")
        self.base_url = base_url.rstrip("/")
        self.pausa = max(pausa_segundos, PAUSA_MINIMA_SEGUNDOS)
        self.reintentos = reintentos
        self.espera_base = espera_base_segundos
        self._dormir = dormir
        self._reloj = reloj
        self._ultima_solicitud: float | None = None
        self._robots: Robots | None = None
        self.solicitudes = 0
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"User-Agent": user_agent},
            timeout=30.0,
            follow_redirects=True,
            transport=transport,
        )

    def cerrar(self) -> None:
        self._http.close()

    def __enter__(self) -> "ClienteSurdoc":
        return self

    def __exit__(self, *_) -> None:
        self.cerrar()

    def _esperar_turno(self) -> None:
        if self._ultima_solicitud is not None:
            faltante = self.pausa - (self._reloj() - self._ultima_solicitud)
            if faltante > 0:
                self._dormir(faltante)
        self._ultima_solicitud = self._reloj()

    def _cargar_robots(self) -> Robots:
        if self._robots is None:
            self._robots = Robots(self._get("/robots.txt", None, verificar_robots=False))
        return self._robots

    def permitido(self, ruta: str) -> bool:
        return self._cargar_robots().permitido(self._http.headers["User-Agent"], ruta)

    def obtener(self, ruta: str, params: dict[str, str] | None = None) -> str:
        """Descarga una ruta de SURDOC y devuelve el HTML."""
        return self._get(ruta, params, verificar_robots=True)

    def _get(self, ruta: str, params: dict[str, str] | None, verificar_robots: bool) -> str:
        if verificar_robots and not self.permitido(ruta):
            raise RutaProhibida(f"robots.txt no permite {ruta}")
        ultimo_error = "sin intentos"
        for intento in range(self.reintentos + 1):
            self._esperar_turno()
            self.solicitudes += 1
            try:
                respuesta = self._http.get(ruta, params=params)
            except httpx.TransportError as error:
                ultimo_error = f"error de red: {error!r}"
                espera = self.espera_base * 2**intento
            else:
                if respuesta.status_code == 200:
                    return respuesta.text
                if respuesta.status_code not in ESTADOS_REINTENTABLES:
                    raise ErrorDescarga(
                        f"HTTP {respuesta.status_code} en {ruta}", respuesta.status_code
                    )
                ultimo_error = f"HTTP {respuesta.status_code}"
                espera = self.espera_base * 2**intento
                retry_after = respuesta.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    espera = max(espera, float(retry_after))
            if intento < self.reintentos:
                log.warning(
                    "%s en %s; reintento %d en %.0f s", ultimo_error, ruta, intento + 1, espera
                )
                self._dormir(espera)
        raise ErrorDescarga(f"{ultimo_error} en {ruta} tras {self.reintentos + 1} intentos")
