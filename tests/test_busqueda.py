"""Pruebas de la búsqueda semántica (Sprint 4).

Usan un codificador falso (bolsa de palabras) para no descargar el modelo real en CI. La
evaluación con el modelo real se corre con EVALUAR_EMBEDDINGS=1 (requiere `--group embed`)."""

import hashlib
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

import httpx
import pytest

from pipeline import db
from pipeline.embed.codificador import prefijos, vector_sql
from pipeline.embed.proceso import (
    buscar,
    evaluar,
    generar_embeddings,
    informe_evaluacion,
    textos_fichas,
)
from pipeline.parse.ficha import parsear_ficha
from tests.conftest import html_ficha

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))
from datos import FuentePostgres, FuenteSupabase  # noqa: E402

FICHAS = ["16-447", "16-872", "16-919", "16-924", "16-989", "16-1771", "16-3366", "16-907"]
EVALUACION = Path(__file__).parents[1] / "evaluacion" / "consultas_busqueda.csv"
DIM = 64


class CodificadorPalabras:
    """Vector = palabras (sin acentos) repartidas por hash en 64 dimensiones, normalizado."""

    def __init__(self, modelo="palabras-64"):
        self.modelo = modelo
        self.llamadas = 0

    def codificar(self, textos, son_consultas=False):
        self.llamadas += 1
        vectores = []
        for texto in textos:
            plano = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
            v = [0.0] * DIM
            for palabra in re.findall(r"[a-z]{4,}", plano):
                v[int(hashlib.md5(palabra[:6].encode()).hexdigest(), 16) % DIM] += 1
            norma = math.sqrt(sum(x * x for x in v)) or 1
            vectores.append([x / norma for x in v])
        return vectores


@pytest.fixture
def bd_busqueda(bd):
    museo = db.obtener_museo_id(bd, 16)
    for i in FICHAS:
        db.guardar_ficha(bd, parsear_ficha(html_ficha(i), i), f"u/{i}", museo)
    return bd


def test_prefijos_e5():
    assert prefijos("intfloat/multilingual-e5-small") == ("query: ", "passage: ")
    assert prefijos("otro/modelo") == ("", "")
    assert vector_sql([0.5, -0.25]) == "[0.500000,-0.250000]"


def test_texto_solo_con_campos_publicos(bd_busqueda):
    textos = textos_fichas(bd_busqueda)
    assert set(textos) == set(FICHAS)
    assert "Rey Felipe" not in textos["16-989"]  # nombre de sitio: nunca en embeddings
    assert "Canoa monóxila" in textos["16-447"] and "Kawésqar" in textos["16-447"]


def test_generacion_incremental(bd_busqueda):
    cod = CodificadorPalabras()
    r = generar_embeddings(bd_busqueda, cod)
    assert (r.fichas, r.pendientes, r.generados) == (8, 8, 8)
    assert generar_embeddings(bd_busqueda, cod).pendientes == 0
    # Si cambia la ficha, cambia su texto y solo ella vuelve a quedar pendiente.
    cambiada = html_ficha("16-907").replace("Varilla de madera", "Varilla de madera nativa", 1)
    db.guardar_ficha(
        bd_busqueda, parsear_ficha(cambiada, "16-907"), "u", db.obtener_museo_id(bd_busqueda, 16)
    )
    r = generar_embeddings(bd_busqueda, cod)
    assert (r.pendientes, r.generados) == (1, 1)
    ejecucion = bd_busqueda.execute(
        "select tipo_proceso, registros_procesados from ejecuciones order by id desc limit 1"
    ).fetchone()
    assert ejecucion == ("embeddings", 1)


def test_busqueda_como_anonimo_y_por_modelo(bd_busqueda):
    cod = CodificadorPalabras()
    generar_embeddings(bd_busqueda, cod)
    generar_embeddings(bd_busqueda, CodificadorPalabras("otro-modelo"))
    resultados = buscar(bd_busqueda, cod, "canoa de madera tallada", 3)
    assert resultados[0][0] == "16-447" and len(resultados) == 3
    # Fichas dadas de baja no aparecen.
    bd_busqueda.execute("update registros set dado_de_baja = true where surdoc_id = '16-447'")
    assert "16-447" not in [s for s, _ in buscar(bd_busqueda, cod, "canoa de madera tallada", 8)]


def test_evaluacion_e_informe(bd_busqueda, tmp_path):
    cod = CodificadorPalabras()
    generar_embeddings(bd_busqueda, cod)
    consultas = tmp_path / "c.csv"
    consultas.write_text(
        "consulta,pertinentes,criterio\n"
        "canoa monóxila,16-447,x\n"
        "sombrero de terciopelo,16-3366,y\n",
        encoding="utf-8",
    )
    resultados = evaluar(bd_busqueda, cod, consultas, k=3)
    assert [r.aciertos for r in resultados] == [1, 1]
    assert "2/2" in informe_evaluacion(resultados, 3)


def test_fuentes_de_la_app(bd_busqueda):
    cod = CodificadorPalabras()
    generar_embeddings(bd_busqueda, cod)
    vector = vector_sql(cod.codificar(["sombrero de terciopelo"], True)[0])
    filas = FuentePostgres(con=bd_busqueda).buscar(vector, cod.modelo, 2)
    assert filas[0]["surdoc_id"] == "16-3366" and 0 < filas[0]["similitud"] <= 1

    peticiones = []

    def manejador(p):
        peticiones.append(p)
        return httpx.Response(200, json=[{"surdoc_id": "16-1", "similitud": 0.9}])

    fuente = FuenteSupabase(
        "https://x.supabase.co", "anon", transport=httpx.MockTransport(manejador)
    )
    assert fuente.buscar("[0.1]", "m", 5) == [{"surdoc_id": "16-1", "similitud": 0.9}]
    assert peticiones[0].url.path == "/rest/v1/rpc/buscar_fichas"
    assert json.loads(peticiones[0].content) == {
        "consulta": "[0.1]",
        "modelo_busqueda": "m",
        "limite": 5,
    }
    assert peticiones[0].headers["Authorization"] == "Bearer anon"


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="requiere Postgres local")
def test_pagina_buscar_carga_sin_consulta(monkeypatch):
    from streamlit.testing.v1 import AppTest

    directorio = Path(__file__).parents[1] / "app"
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.chdir(directorio)
    prueba = AppTest.from_file(str(directorio / "buscar.py"), default_timeout=60).run()
    assert not prueba.exception, prueba.exception
    assert prueba.title[0].value == "Buscar en la colección"


@pytest.mark.skipif(
    not os.environ.get("EVALUAR_EMBEDDINGS"),
    reason="modelo real: EVALUAR_EMBEDDINGS=1 y --group embed",
)
def test_criterio_sprint4_con_el_modelo_real(conexion_bd):
    """Criterio de aceptación: 10 consultas con resultados pertinentes en los 5 primeros.
    Usa los datos y embeddings ya cargados en la base (no la revierte)."""
    from pipeline.embed.codificador import CodificadorSentenceTransformers

    cod = CodificadorSentenceTransformers()
    generar_embeddings(conexion_bd, cod)
    resultados = evaluar(conexion_bd, cod, EVALUACION, 5)
    assert len(resultados) == 10
    assert all(r.aciertos > 0 for r in resultados), informe_evaluacion(resultados)
