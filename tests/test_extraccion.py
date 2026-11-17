"""Prueba de punta a punta de la extracción contra Postgres real, con SURDOC simulado.
Cada prueba corre en una transacción que se revierte."""

import httpx
import pytest

from pipeline.extract.cliente import ClienteSurdoc
from pipeline.extract.extraccion import ejecutar_extraccion
from tests.conftest import html_ficha

ROBOTS = "User-agent: *\nDisallow: /registro/*/pdf\n"


def html_listado(ids: list[str], total: int) -> str:
    filas = "".join(
        f'<div class="views-row"><a href="/registro/{i}" class="record-title">x</a></div>'
        for i in ids
    )
    return (
        f'<a data-drupal-facet-item-id="institution-16" data-drupal-facet-item-count="{total}"></a>'
        f"<div>{total} registros</div>{filas}"
    )


class SurdocFalso:
    """Simula el sitio: listado paginado de a 2 y fichas tomadas de las fixtures."""

    def __init__(self, ids, total=None, rotas=(), caidas=(), modificadas=None):
        self.ids, self.total = list(ids), total
        self.rotas, self.caidas = set(rotas), set(caidas)
        self.modificadas = modificadas or {}

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        ruta = peticion.url.path
        if ruta == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        if ruta == "/colecciones":
            pagina = int(peticion.url.params["page"])
            total = len(self.ids) if self.total is None else self.total
            return httpx.Response(
                200, text=html_listado(self.ids[pagina * 2 : pagina * 2 + 2], total)
            )
        surdoc_id = ruta.removeprefix("/registro/")
        if surdoc_id in self.caidas:
            return httpx.Response(404)
        if surdoc_id in self.rotas:
            return httpx.Response(200, text="<html><body>Sitio en mantenimiento</body></html>")
        return httpx.Response(200, text=self.modificadas.get(surdoc_id) or html_ficha(surdoc_id))


def extraer(bd, sitio, **kwargs):
    cliente = ClienteSurdoc(
        "https://www.surdoc.cl", "ObservatorioPruebas/0.1", transport=httpx.MockTransport(sitio),
        dormir=lambda _: None, reintentos=0,
    )  # fmt: skip
    return ejecutar_extraccion(bd, cliente, 16, 548, **kwargs)


def contar(bd, sql, *params):
    return bd.execute(sql, params).fetchone()[0]


IDS = ["16-447", "16-919", "16-989", "16-1771"]


def test_carga_bronce_plata_terminos_y_ejecucion(bd):
    r = extraer(bd, SurdocFalso(IDS))
    assert (r.listados, r.nuevas_o_cambiadas, r.sin_cambios, r.en_cuarentena) == (4, 4, 0, [])
    assert contar(bd, "select count(*) from registros_raw where surdoc_id = any(%s)", IDS) == 4
    assert contar(bd, "select count(*) from registros where surdoc_id = any(%s)", IDS) == 4
    fila = bd.execute(
        "select objeto, tecnica_material, cultura_originaria, url_imagen, credito_imagen "
        "from registros where surdoc_id = '16-447'"
    ).fetchone()
    assert fila[0] == "Canoa monóxila" and fila[1] == "Tallado - Madera; Ahuecar - Madera"
    assert (
        fila[2] == "Kawésqar"
        and fila[3].endswith("canoa_16-447.jpg")
        and fila[4] == "Franklin Pardon"
    )
    terminos = bd.execute(
        "select campo, orden, grupo, texto_original, fuente_termino, id_termino "
        "from registro_terminos where surdoc_id = '16-919' order by campo, orden"
    ).fetchall()
    assert terminos == [
        ("material", 0, 0, "Piedra", "aat", "300011176"),
        ("material", 1, 0, "Cuero (material animal)", "aat", "300011845"),
        ("objeto", 0, None, "Boleadora", "aat", "300036998"),
    ]
    # Nombre de sitio: en bronce sí, en plata no existe la columna.
    assert (
        contar(bd, "select campos->>'nombre_sitio' from registros_raw where surdoc_id = '16-989'")
        == "Rey Felipe"
    )
    ejecucion = bd.execute(
        "select tipo_proceso, fin is not null, registros_procesados, en_cuarentena, errores "
        "from ejecuciones order by id desc limit 1"
    ).fetchone()
    assert ejecucion == ("extraccion", True, 4, 0, 0)


def test_reejecutar_no_duplica_ni_reescribe(bd):
    extraer(bd, SurdocFalso(IDS))
    antes = bd.execute(
        "select surdoc_id, fecha_extraccion from registros_raw "
        "where surdoc_id = any(%s) order by 1",
        (IDS,),
    ).fetchall()
    terminos_antes = contar(
        bd, "select count(*) from registro_terminos where surdoc_id = any(%s)", IDS
    )
    r = extraer(bd, SurdocFalso(IDS))
    assert (r.nuevas_o_cambiadas, r.sin_cambios) == (0, 4)
    despues = bd.execute(
        "select surdoc_id, fecha_extraccion from registros_raw "
        "where surdoc_id = any(%s) order by 1",
        (IDS,),
    ).fetchall()
    assert antes == despues
    assert (
        contar(bd, "select count(*) from registro_terminos where surdoc_id = any(%s)", IDS)
        == terminos_antes
    )


def test_ficha_rota_o_caida_va_a_cuarentena_sin_detener_el_lote(bd):
    r = extraer(bd, SurdocFalso(IDS, rotas={"16-919"}, caidas={"16-989"}))
    assert sorted(r.en_cuarentena) == ["16-919", "16-989"]
    assert r.nuevas_o_cambiadas == 2
    errores = dict(bd.execute(
        "select surdoc_id, error from cuarentena where surdoc_id in ('16-919', '16-989')"
    ).fetchall())  # fmt: skip
    assert errores["16-919"].startswith("parseo:") and errores["16-989"].startswith("descarga:")
    assert contar(bd, "select html from cuarentena where surdoc_id = '16-919'").startswith("<html>")
    assert contar(bd, "select en_cuarentena from ejecuciones order by id desc limit 1") == 2


def test_ficha_que_desaparece_queda_dada_de_baja_y_vuelve_si_reaparece(bd):
    extraer(bd, SurdocFalso(IDS))
    r = extraer(bd, SurdocFalso(["16-447", "16-919", "16-1771"]))
    assert r.dadas_de_baja == ["16-989"]
    assert contar(bd, "select dado_de_baja from registros where surdoc_id = '16-989'") is True
    assert (
        contar(bd, "select count(*) from registros_raw where surdoc_id = '16-989'") == 1
    )  # no se borra
    extraer(bd, SurdocFalso(IDS))
    assert contar(bd, "select dado_de_baja from registros where surdoc_id = '16-989'") is False


def test_listado_incompleto_no_marca_bajas(bd):
    extraer(bd, SurdocFalso(IDS))
    r = extraer(bd, SurdocFalso(["16-447"], total=4))  # SURDOC dice 4 pero solo se listó 1
    assert r.dadas_de_baja == [] and "incompleto" in r.bajas_omitidas
    assert (
        contar(bd, "select count(*) from registros where dado_de_baja and surdoc_id = any(%s)", IDS)
        == 0
    )


def test_cambio_en_la_ficha_se_detecta_por_hash(bd):
    extraer(bd, SurdocFalso(IDS))
    cambiada = html_ficha("16-447").replace(">Regular<", ">Bueno<", 1)
    r = extraer(bd, SurdocFalso(IDS, modificadas={"16-447": cambiada}))
    assert (r.nuevas_o_cambiadas, r.sin_cambios) == (1, 3)
    assert (
        contar(bd, "select estado_conservacion from registros where surdoc_id = '16-447'")
        == "Bueno"
    )


def test_limite_no_marca_bajas(bd):
    r = extraer(bd, SurdocFalso(IDS), limite=2)
    assert r.procesadas == 2 and r.bajas_omitidas == "ejecución con límite"


def test_museo_inexistente_falla_claro(bd):
    cliente = ClienteSurdoc(
        "https://www.surdoc.cl", "x", transport=httpx.MockTransport(SurdocFalso(IDS))
    )
    with pytest.raises(LookupError, match="9999"):
        ejecutar_extraccion(bd, cliente, 9999, 548)
