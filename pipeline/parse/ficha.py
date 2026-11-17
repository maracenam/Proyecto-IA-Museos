"""HTML de una ficha de SURDOC → modelo Ficha.

Estructura verificada en el Sprint 0 (docs/sprint0.md §3): campos simples en
div.field--inline identificados por su clase field--name-*, bloque de objeto en
div.field--name-object, pares técnica/material en div.technical-item y carrusel
de imágenes en a.litebox."""

import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString, Tag
from pydantic import ValidationError

from pipeline.parse.modelos import Ficha, Imagen, Termino

_ENLACE_TERMINO = re.compile(r"(aatespanol|tesauroregional)\.cl/terminos/(\d+)")
_FUENTES = {"aatespanol": "aat", "tesauroregional": "tesauro_regional"}

# Clase field--name-* de SURDOC → atributo de Ficha.
CAMPOS_POR_CLASE = {
    "record-number": "_numero_registro",
    "inventory-numbers": "numero_inventario",
    "second-level-classification": "clasificacion",
    "collection": "coleccion",
    "physical-description": "descripcion",
    "conservation-state": "estado_conservacion",
    "provenance": "procedencia",
    "cult-original-culture": "cultura_originaria",
    "cult-archaeological-culture": "cultura_arqueologica",
    "hist-geo-geographic-area": "area_geografica",
    "archa-site-name": "nombre_sitio",
    "ingress-mode": "forma_ingreso",
    "ingress-date": "fecha_ingreso",
    "hist-geo-history": "historia_objeto",
    "hist-geo-ownership-use-history": "historia_propiedad_uso",
}
# Campos sin clase conocida (no aparecen en Magallanes): se buscan por etiqueta.
CAMPOS_POR_ETIQUETA = {"Fecha de creación": "fecha_creacion", "Creador": "creador"}
AREA_CULTURAL = ("archa-first-level-cultural-area", "archa-second-level-cultural-area")
ETIQUETAS_OBJETO = {
    "Dimensiones": "dimensiones",
    "Ubicación": "ubicacion",
    "Situación": "situacion",
}


class ErrorParseo(Exception):
    """La ficha no tiene la estructura esperada; va a cuarentena."""


def _limpiar(texto: str) -> str:
    texto = " ".join(texto.split())
    return re.sub(r"\s+([,;.])", r"\1", texto)


def _texto(elemento: Tag) -> str:
    return _limpiar(elemento.get_text(" ", strip=True))


def _termino_de_enlace(enlace: Tag | None) -> tuple[str | None, str | None]:
    if enlace is None or not enlace.get("href"):
        return None, None
    coincidencia = _ENLACE_TERMINO.search(enlace["href"])
    if not coincidencia:
        return None, None
    return _FUENTES[coincidencia.group(1)], coincidencia.group(2)


def _items_de_campo(campo: Tag) -> list[Tag]:
    items = campo.select(":scope > div.field-item, :scope > div.field-items > div.field-item")
    return items or campo.select("div.field-item")[:1]


def _nombre_campo(campo: Tag) -> str | None:
    for clase in campo.get("class", []):
        if clase.startswith("field--name-"):
            return clase.removeprefix("field--name-")
    return None


def _partes_tecnica_material(item: Tag) -> list[list[tuple[str, Tag | None]]]:
    """Divide un div.technical-item en segmentos separados por " - " (técnica, material),
    y cada segmento en valores separados por coma, conservando el enlace de cada valor."""
    enlaces: list[Tag] = []
    plano = []
    for nodo in item.children:
        if isinstance(nodo, Tag) and nodo.name == "a":
            plano.append(f"\x00{len(enlaces)}\x00")
            enlaces.append(nodo)
        elif isinstance(nodo, NavigableString):
            plano.append(str(nodo))
        elif isinstance(nodo, Tag):
            plano.append(nodo.get_text(" "))
    segmentos = []
    for segmento in re.split(r"\s+-\s+", "".join(plano)):
        valores = []
        for valor in segmento.split(","):
            valor = valor.strip()
            if not valor:
                continue
            marca = re.fullmatch(r"\x00(\d+)\x00", valor)
            if marca:
                enlace = enlaces[int(marca.group(1))]
                valores.append((_texto(enlace), enlace))
            else:
                valores.append((_limpiar(re.sub(r"\x00\d+\x00", "", valor)), None))
        if valores:
            segmentos.append(valores)
    return segmentos


def parsear_ficha(html: str, surdoc_id: str, base_url: str = "https://www.surdoc.cl") -> Ficha:
    sopa = BeautifulSoup(html, "html.parser")
    datos: dict = {"surdoc_id": surdoc_id, "institucion": int(surdoc_id.split("-")[0])}
    otros: dict[str, tuple[str, ...]] = {}
    terminos: list[Termino] = []
    orden = {"objeto": 0, "nombre_alternativo": 0, "tecnica": 0, "material": 0}

    def agregar_termino(campo: str, texto: str, enlace: Tag | None, grupo: int | None = None):
        fuente, id_termino = _termino_de_enlace(enlace)
        terminos.append(
            Termino(
                campo=campo,
                orden=orden[campo],
                grupo=grupo,
                texto=texto,
                fuente=fuente,
                id_termino=id_termino,
            )
        )
        orden[campo] += 1

    titulo = sopa.find("title")
    if titulo:
        datos["titulo"] = _limpiar(titulo.get_text()).removesuffix("| SURDOC").strip()

    # Campos simples
    areas = {}
    for campo in sopa.select("div.field.field--inline"):
        etiqueta_el = campo.select_one(":scope > div.field-label") or campo.select_one(
            "div.field-label"
        )
        if etiqueta_el is None:
            continue
        etiqueta = _texto(etiqueta_el)
        valores = tuple(v for v in (_texto(i) for i in _items_de_campo(campo)) if v)
        if not valores:
            continue
        otros.setdefault(etiqueta, valores)
        nombre = _nombre_campo(campo)
        if nombre in AREA_CULTURAL:
            areas[nombre] = valores[0]
        elif nombre in CAMPOS_POR_CLASE:
            datos.setdefault(CAMPOS_POR_CLASE[nombre], "; ".join(valores))
        elif etiqueta in CAMPOS_POR_ETIQUETA:
            datos.setdefault(CAMPOS_POR_ETIQUETA[etiqueta], "; ".join(valores))
    if areas:
        datos["area_cultural"] = " / ".join(areas[n] for n in AREA_CULTURAL if n in areas)

    # Bloque de objeto
    objetos, alternativos, pares = [], [], []
    for item in sopa.select("div.field--name-object div.form-item"):
        etiqueta_el = item.select_one("label.form-item__label")
        valor_el = item.select_one("div.field-item")
        if etiqueta_el is None or valor_el is None:
            continue
        etiqueta = _texto(etiqueta_el)
        if etiqueta in ("Objeto", "Nombre alternativo"):
            campo = "objeto" if etiqueta == "Objeto" else "nombre_alternativo"
            texto = _texto(valor_el)
            if texto:
                agregar_termino(campo, texto, valor_el.find("a"))
                (objetos if campo == "objeto" else alternativos).append(texto)
        elif etiqueta == "Técnica / Material":
            grupos = valor_el.select("div.technical-item")
            otros.setdefault("Objeto / Técnica / Material", tuple(_texto(g) for g in grupos))
            for grupo, tecnico in enumerate(grupos):
                segmentos = _partes_tecnica_material(tecnico)
                if len(segmentos) > 2:
                    raise ErrorParseo(
                        f"Técnica / Material con {len(segmentos)} partes: {_texto(tecnico)!r}"
                    )
                tecnicas = segmentos[0] if len(segmentos) == 2 else []
                materiales = segmentos[-1] if segmentos else []
                for texto, enlace in tecnicas:
                    agregar_termino("tecnica", texto, enlace, grupo)
                for texto, enlace in materiales:
                    agregar_termino("material", texto, enlace, grupo)
                pares.append(_texto(tecnico))
        elif etiqueta in ETIQUETAS_OBJETO:
            datos.setdefault(ETIQUETAS_OBJETO[etiqueta], _texto(valor_el))
        if etiqueta != "Técnica / Material" and _texto(valor_el):
            otros.setdefault(f"Objeto / {etiqueta}", (_texto(valor_el),))
    if objetos:
        datos["objeto"] = "; ".join(objetos)
    if alternativos:
        datos["nombre_alternativo"] = "; ".join(alternativos)
    if pares:
        datos["tecnica_material"] = "; ".join(pares)

    # Imágenes: enlace al archivo en SURDOC (sin parámetros dinámicos) y crédito.
    imagenes, vistas = [], set()
    for enlace in sopa.select("a.litebox[href]"):
        partes = urlsplit(urljoin(base_url + "/", enlace["href"]))
        url = urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))
        if url in vistas:
            continue
        vistas.add(url)
        img = enlace.find("img")
        credito = (img.get("title") or img.get("alt") or "").strip() if img else ""
        imagenes.append(Imagen(url=url, credito=credito or None))

    numero = datos.pop("_numero_registro", None)
    if numero != surdoc_id:
        raise ErrorParseo(
            f"Número de registro {numero!r} no coincide con {surdoc_id!r} (¿cambió el HTML?)"
        )
    try:
        return Ficha(
            **datos, terminos=tuple(terminos), imagenes=tuple(imagenes), otros_campos=otros
        )
    except ValidationError as error:
        raise ErrorParseo(f"Ficha inválida: {error}") from error
