"""Pruebas del parser con fichas reales guardadas en tests/fixtures."""

import re

import pytest
from bs4 import BeautifulSoup

from pipeline.db import fila_registro
from pipeline.parse.ficha import ErrorParseo, parsear_ficha
from tests.conftest import FIXTURES, html_ficha

IDS = sorted(p.stem.removeprefix("registro_") for p in FIXTURES.glob("registro_*.html"))


def ficha(surdoc_id: str):
    return parsear_ficha(html_ficha(surdoc_id), surdoc_id)


def terminos(f, campo):
    return [
        (t.orden, t.grupo, t.texto, t.fuente, t.id_termino) for t in f.terminos if t.campo == campo
    ]


@pytest.mark.parametrize("surdoc_id", IDS)
def test_todas_las_fixtures_se_parsean(surdoc_id):
    f = ficha(surdoc_id)
    assert f.surdoc_id == surdoc_id
    assert f.institucion == 16
    assert f.estado_conservacion in {"Muy bueno", "Bueno", "Regular"}
    assert f.descripcion
    assert f.titulo


def test_campos_simples():
    f = ficha("16-447")
    assert f.titulo == "Canoa monóxila"
    assert f.numero_inventario == "PH-001"
    assert f.clasificacion.endswith("Utensilios, Herramientas y Equipos")
    assert f.coleccion == "Primeros Habitantes"
    assert f.objeto == "Canoa monóxila"
    assert f.nombre_alternativo == "Kájef"
    assert f.dimensiones == "Alto 50 cm - Ancho 44 cm - Largo 474 cm"
    assert f.estado_conservacion == "Regular"
    assert f.cultura_originaria == "Kawésqar"
    assert f.area_cultural == "América / Pampa y Fuego-Patagonia"
    assert f.area_geografica == "Chile"
    assert f.forma_ingreso == "Donación"
    assert f.fecha_ingreso == "1969/1970"


def test_dos_pares_tecnica_material():
    f = ficha("16-447")
    assert f.tecnica_material == "Tallado - Madera; Ahuecar - Madera"
    assert terminos(f, "tecnica") == [
        (0, 0, "Tallado", "aat", "300053149"),
        (1, 1, "Ahuecar", None, None),
    ]
    assert terminos(f, "material") == [
        (0, 0, "Madera", "aat", "300011914"),
        (1, 1, "Madera", "aat", "300011914"),
    ]


def test_varios_materiales_en_un_mismo_par():
    f = ficha("16-919")
    assert terminos(f, "tecnica") == []
    assert terminos(f, "material") == [
        (0, 0, "Piedra", "aat", "300011176"),
        (1, 0, "Cuero (material animal)", "aat", "300011845"),
    ]


def test_objeto_en_tesauro_regional_aat_y_sin_enlace():
    assert terminos(ficha("16-447"), "objeto") == [
        (0, None, "Canoa monóxila", "tesauro_regional", "384")
    ]
    assert terminos(ficha("16-1771"), "objeto") == [(0, None, "Arpón", "aat", "300037011")]
    assert terminos(ficha("16-924"), "objeto") == [(0, None, "Lana", None, None)]


def test_material_en_tesauro_regional():
    assert terminos(ficha("16-1005"), "material") == [
        (0, 0, "Obsidiana", "tesauro_regional", "3696")
    ]


def test_sin_tecnica_material():
    f = ficha("16-1771")
    assert f.tecnica_material is None
    assert not [t for t in f.terminos if t.campo in ("tecnica", "material")]


def test_imagenes_en_ambas_rutas_sin_parametros_dinamicos():
    antigua = ficha("16-447").imagenes
    assert len(antigua) == 5
    assert (
        antigua[0].url == "https://www.surdoc.cl/sites/default/files/record_images/canoa_16-447.jpg"
    )
    assert antigua[0].credito == "Franklin Pardon"
    assert any(i.credito is None for i in antigua)  # una imagen sin crédito
    nueva = ficha("16-1771").imagenes[0]
    assert "/records/images/2025-09/" in nueva.url
    assert all("?" not in i.url for f in IDS for i in ficha(f).imagenes)


def test_ficha_sin_imagen():
    # Caso sintético: en Magallanes no existe una ficha sin imagen (docs/sprint0.md),
    # así que se genera quitando el carrusel de una ficha real.
    sopa = BeautifulSoup(html_ficha("16-907"), "html.parser")
    for carrusel in sopa.select("[data-photoswipe-gallery], a.litebox"):
        carrusel.decompose()
    f = parsear_ficha(str(sopa), "16-907")
    assert f.imagenes == ()
    assert fila_registro(f)["url_imagen"] is None


def test_nombre_sitio_se_guarda_pero_no_pasa_a_plata():
    f = ficha("16-989")
    assert f.nombre_sitio == "Rey Felipe"
    assert f.cultura_arqueologica == "Cazadores-recolectores marítimos (o canoeros)"
    assert f.procedencia == "Centro de Estudios Patagónicos"
    assert "nombre_sitio" not in fila_registro(f)
    assert "Rey Felipe" not in str(fila_registro(f).values())


def test_hash_estable_ante_atributos_dinamicos():
    html = html_ficha("16-447")
    alterado = re.sub(r'data-b-token="[^"]*"', 'data-b-token="b-otro"', html)
    alterado = re.sub(r"itok=[\w-]+", "itok=OTRO", alterado)
    alterado = alterado.replace("<head>", '<head><meta data-once="x">')
    assert alterado != html
    assert parsear_ficha(alterado, "16-447").hash_campos() == ficha("16-447").hash_campos()


def test_hash_cambia_si_cambia_un_campo():
    alterado = html_ficha("16-447").replace(">Regular<", ">Bueno<", 1)
    assert parsear_ficha(alterado, "16-447").hash_campos() != ficha("16-447").hash_campos()


def test_id_que_no_coincide_es_error_de_parseo():
    with pytest.raises(ErrorParseo, match="no coincide"):
        parsear_ficha(html_ficha("16-447"), "16-448")


def test_html_sin_estructura_es_error_de_parseo():
    with pytest.raises(ErrorParseo):
        parsear_ficha("<html><body><h1>Mantenimiento</h1></body></html>", "16-447")
