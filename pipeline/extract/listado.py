"""Listado de fichas de una institución y clasificación en el buscador de SURDOC.

Paginación verificada en el Sprint 0: page=0..N, 21 fichas por página; una página
fuera de rango devuelve 0 fichas."""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from pipeline.extract.cliente import ClienteSurdoc

RUTA_LISTADO = "/colecciones"
_ID = re.compile(r"/registro/(\d+-\d+)$")
_TOTAL = re.compile(r"(\d[\d.]*)\s+registros?\b")


@dataclass(frozen=True)
class PaginaListado:
    ids: list[str]
    total: int | None


@dataclass(frozen=True)
class Listado:
    ids: list[str]
    total_informado: int | None
    paginas: int

    @property
    def completo(self) -> bool:
        """True si se recogieron tantas fichas como SURDOC dice tener."""
        return self.total_informado is not None and len(self.ids) == self.total_informado


def parametros_listado(institucion: int, clasificacion: int, pagina: int) -> dict[str, str]:
    return {
        "f[0]": f"institution:{institucion}",
        "first_level_classification": str(clasificacion),
        "query": "",
        "page": str(pagina),
    }


def parsear_listado(html: str, institucion: int) -> PaginaListado:
    sopa = BeautifulSoup(html, "html.parser")
    ids: list[str] = []
    # Cualquier enlace de la tarjeta: una ficha sin "Objeto" (16-972) no trae a.record-title,
    # pero sí el enlace "Ver" (a.record-view-sheet).
    for enlace in sopa.select('div.views-row a[href^="/registro/"]'):
        coincidencia = _ID.search(enlace["href"])
        if coincidencia and coincidencia.group(1).startswith(f"{institucion}-"):
            if coincidencia.group(1) not in ids:
                ids.append(coincidencia.group(1))
    total = None
    faceta = sopa.select_one(f'[data-drupal-facet-item-id="institution-{institucion}"]')
    if faceta and faceta.get("data-drupal-facet-item-count", "").isdigit():
        total = int(faceta["data-drupal-facet-item-count"])
    else:
        coincidencia = _TOTAL.search(sopa.get_text(" "))
        if coincidencia:
            total = int(coincidencia.group(1).replace(".", ""))
    return PaginaListado(ids=ids, total=total)


def listar_ids(
    cliente: ClienteSurdoc, institucion: int, clasificacion: int, max_paginas: int = 500
) -> Listado:
    ids: list[str] = []
    total = None
    for pagina in range(max_paginas):
        html = cliente.obtener(RUTA_LISTADO, parametros_listado(institucion, clasificacion, pagina))
        resultado = parsear_listado(html, institucion)
        if total is None:
            total = resultado.total
        if not resultado.ids:
            return Listado(ids=ids, total_informado=total, paginas=pagina)
        ids.extend(i for i in resultado.ids if i not in ids)
    raise RuntimeError(f"El listado superó {max_paginas} páginas sin terminar.")
