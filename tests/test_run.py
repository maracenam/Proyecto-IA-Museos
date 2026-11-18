"""Pruebas del punto de entrada de la extracción (códigos de salida y resumen para GitHub)."""

import pytest

from pipeline import run
from pipeline.extract.extraccion import Resumen
from pipeline.run import ResultadoMuseo, codigo_salida, museos_a_extraer, resumen_markdown


def resultado(nuevas=0, sin_cambios=77, cuarentena=0, error=None, bajas_omitidas=None):
    if error:
        return ResultadoMuseo(16, "Museo Regional de Magallanes", error=error)
    resumen = Resumen(
        total_informado=77, listados=77, nuevas_o_cambiadas=nuevas, sin_cambios=sin_cambios,
        en_cuarentena=[f"16-{i}" for i in range(cuarentena)], bajas_omitidas=bajas_omitidas,
    )  # fmt: skip
    return ResultadoMuseo(16, "Museo Regional de Magallanes", resumen)


def test_corrida_normal_sale_con_cero():
    assert codigo_salida([resultado(), resultado(cuarentena=2, sin_cambios=75)]) == 0


def test_error_de_un_museo_sale_con_uno():
    assert codigo_salida([resultado(), resultado(error="ErrorDescarga: HTTP 503")]) == 1


def test_mucha_cuarentena_alerta_cambio_de_html():
    # 30 de 77 en cuarentena (39 %): probablemente SURDOC cambió su HTML.
    r = resultado(cuarentena=30, sin_cambios=47)
    assert r.proporcion_cuarentena == pytest.approx(30 / 77)
    assert codigo_salida([r]) == 2
    assert "demasiada cuarentena" in resumen_markdown([r])


def test_resumen_markdown():
    texto = resumen_markdown([resultado(nuevas=3, sin_cambios=74), resultado(error="X: y")])
    assert "| Museo Regional de Magallanes (16) | 77 (77) | 3 | 74 | 0 | 0 | ✅ |" in texto
    assert "❌ X: y" in texto


def test_museos_a_extraer(bd):
    bd.execute(
        "insert into museos (nombre, codigo_institucion) values ('Museo de prueba', 9999) "
        "on conflict do nothing"
    )
    todos = museos_a_extraer(bd, None)
    assert (16, "Museo Regional de Magallanes") in todos and (9999, "Museo de prueba") in todos
    assert museos_a_extraer(bd, 16) == [(16, "Museo Regional de Magallanes")]


def test_main_exige_museo_o_todos():
    with pytest.raises(SystemExit):
        run.main([])
    with pytest.raises(SystemExit):
        run.main(["--museo", "16", "--todos"])
