"""Verifica que las fichas guardadas en tests/fixtures conservan la estructura de SURDOC
documentada en el Sprint 0 (docs/sprint0.md). Si SURDOC cambia su HTML, volver a
descargar las fixtures hará fallar estas pruebas antes de que falle el parser."""

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

FIXTURES = Path(__file__).parent / "fixtures"
FICHAS = sorted(FIXTURES.glob("registro_*.html"))


def cargar(nombre: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / nombre).read_text(encoding="utf-8"), "html.parser")


def test_hay_suficientes_fichas():
    assert 5 <= len(FICHAS) <= 12


@pytest.mark.parametrize("ruta", FICHAS, ids=lambda p: p.stem)
def test_ficha_tiene_campos_basicos(ruta: Path):
    sopa = BeautifulSoup(ruta.read_text(encoding="utf-8"), "html.parser")
    surdoc_id = ruta.stem.removeprefix("registro_")
    numero = sopa.select_one("div.field--name-record-number div.field-item")
    assert numero is not None and numero.get_text(strip=True) == surdoc_id
    assert sopa.select_one("div.field--name-conservation-state div.field-item") is not None
    assert sopa.select_one("div.field--name-object label.form-item__label") is not None


def test_varios_pares_tecnica_material_con_enlaces():
    sopa = cargar("registro_16-447.html")
    pares = sopa.select("div.field--name-object div.technical-item")
    assert len(pares) == 2
    textos = [" ".join(p.get_text(" ", strip=True).split()) for p in pares]
    assert textos == ["Tallado - Madera", "Ahuecar - Madera"]
    assert pares[0].select_one('a[href$="/terminos/300053149"]') is not None


def test_objeto_enlaza_tesauro_regional_o_aat():
    tesauro = cargar("registro_16-447.html").select_one("div.field--name-object a")
    aat = cargar("registro_16-1771.html").select_one("div.field--name-object a")
    assert "tesauroregional.cl/terminos/384" in tesauro["href"]
    assert "aatespanol.cl/terminos/300037011" in aat["href"]


def test_objeto_sin_enlace():
    objeto = cargar("registro_16-924.html").select_one("div.field--name-object div.field-item")
    assert objeto.get_text(strip=True) == "Lana"
    assert objeto.find("a") is None


def test_imagenes_en_ambas_rutas_con_credito():
    antigua = cargar("registro_16-447.html").select_one("a.litebox")
    nueva = cargar("registro_16-1771.html").select_one("a.litebox")
    assert "/record_images/" in antigua["href"]
    assert "/records/images/" in nueva["href"]
    assert nueva.img["title"] == "Franklin Pardon"


def test_nombre_sitio_existe_y_es_dato_sensible():
    sopa = cargar("registro_16-989.html")
    sitio = sopa.select_one("div.field--name-archa-site-name div.field-item")
    assert sitio is not None and sitio.get_text(strip=True)


def test_listado_paginado():
    p0 = (FIXTURES / "listado_548_16_p0.html").read_text(encoding="utf-8")
    p3 = (FIXTURES / "listado_548_16_p3.html").read_text(encoding="utf-8")
    assert "77 registros" in p0
    assert 'data-drupal-facet-item-count="77"' in p0
    assert len(set(re.findall(r'href="/registro/(16-\d+)"', p0))) == 21
    assert len(set(re.findall(r'href="/registro/(16-\d+)"', p3))) == 14
    assert "page=3" in p0
