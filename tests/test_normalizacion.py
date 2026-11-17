"""Pruebas de la normalización: vocabulario, reglas, LLM (simulado), proceso y calidad."""

import csv
import json

import httpx
import pytest

from pipeline import db
from pipeline.normalize.calidad import (
    FilaRevisada,
    calcular_metricas,
    exportar_muestra,
    informe_markdown,
    leer_revision,
)
from pipeline.normalize.llm import (
    ModeloNoDisponible,
    NormalizadorOllama,
    Prompt,
    RespuestaInvalida,
    RespuestaLLM,
)
from pipeline.normalize.proceso import (
    construir_casos,
    consultar_llm,
    ejecutar_normalizacion,
    filtrar_pendientes,
)
from pipeline.normalize.reglas import Caso, aplicar_reglas
from pipeline.normalize.vocabulario import Categoria, TerminoVocab, Vocabulario, sin_acentos
from pipeline.parse.ficha import parsear_ficha
from tests.conftest import html_ficha

VOCAB = Vocabulario.cargar()
PROMPT = Prompt.cargar("v1")


def caso(campo, entrada, fuente=None, id_termino=None, origen="termino", **contexto):
    return Caso("16-1", campo, 0, origen, entrada, fuente, id_termino, contexto)


class NormalizadorFalso:
    """Responde según una función; registra las llamadas."""

    modelo = "falso:1b"

    def __init__(self, responder):
        self.responder = responder
        self.llamadas = []

    def proponer(self, sistema, mensaje, categorias):
        self.llamadas.append((sistema, mensaje, categorias))
        return self.responder(mensaje, categorias)


def siempre(valor, confianza=0.7):
    return lambda _m, _c: RespuestaLLM(valor=valor, confianza=confianza, justificacion="prueba")


# --- Vocabulario ---


def test_vocabulario_carga_y_es_coherente():
    assert "fibra vegetal" in VOCAB.nombres_categoria("material")
    assert VOCAB.nombres_categoria("objeto")[-1] == "otro"
    assert VOCAB.por_id("material", "aat", "300011176").categoria == "lítico"
    assert VOCAB.por_id("material", "tesauro_regional", "3696").categoria == "lítico"
    assert VOCAB.por_texto("objeto", "PUNTA DE ARPON").categoria == "proyectil y arma"


def test_categoria_inexistente_en_terminos_es_error():
    cats = [Categoria("material", "lítico", "", ())]
    malo = [TerminoVocab("material", "aat", "1", "Piedra", (), None, "piedrita")]
    with pytest.raises(ValueError, match="piedrita"):
        Vocabulario(cats, malo)


def test_palabras_clave_sin_acentos_y_palabra_completa():
    assert sin_acentos("  Fragmento CERÁMICO ") == "fragmento ceramico"
    assert VOCAB.categorias_en_texto("material", "Objeto lítico de obsidiana") == {"lítico"}
    assert VOCAB.categorias_en_texto("material", "Tejida con junquillo") == {"fibra vegetal"}
    assert VOCAB.categorias_en_texto("material", "pedrería") == set()


# --- Reglas ---


def test_regla_por_id():
    p = aplicar_reglas(caso("material", "Piedra", "aat", "300011176"), VOCAB)
    assert (p.valor, p.metodo, p.confianza) == ("lítico", "regla_id", 0.99)


def test_regla_por_sinonimo_sin_enlace():
    p = aplicar_reglas(caso("objeto", "Fragmento de hueso"), VOCAB)
    assert (p.valor, p.metodo, p.confianza) == ("fragmento", "sinonimo", 0.95)


def test_sin_regla_va_al_llm():
    assert aplicar_reglas(caso("objeto", "Guaica", "tesauro_regional", "3757"), VOCAB) is None
    assert aplicar_reglas(caso("material", "Objeto lítico", origen="descripcion"), VOCAB) is None


def test_conflicto_con_la_descripcion_baja_la_confianza():
    descripcion = "Fragmento cerámico monocromático, pasta uniforme."  # 16-872
    p = aplicar_reglas(
        caso("material", "Madera", "aat", "300011914", descripcion=descripcion,
             materiales_declarados=(("Madera", "aat", "300011914"),)),
        VOCAB,
    )  # fmt: skip
    assert p.valor == "madera" and p.confianza == 0.5 and "cerámica" in p.justificacion


def test_sin_conflicto_si_la_descripcion_menciona_otro_material_declarado():
    declarados = (("Piedra", "aat", "300011176"), ("Cuero (material animal)", "aat", "300011845"))
    p = aplicar_reglas(
        caso("material", "Piedra", "aat", "300011176",
             descripcion="Pesos esféricos revestidos en cuero", materiales_declarados=declarados),
        VOCAB,
    )  # fmt: skip
    assert p.confianza == 0.99  # 16-919


# --- LLM ---


def test_prompt_incluye_categorias_y_contexto():
    cats = [(c.nombre, c.descripcion) for c in VOCAB.categorias("material")]
    sistema = PROMPT.sistema("material", cats)
    assert "- fibra vegetal: Junco" in sistema and '"valor"' in sistema
    c = caso("material", "Tejida con junquillo", origen="descripcion", objeto="Canasto",
             descripcion="Tejida con junquillo")  # fmt: skip
    mensaje = Prompt.mensaje(c)
    assert "(la ficha no lo declara)" in mensaje and "Objeto: Canasto" in mensaje


def ollama_con(manejador):
    return NormalizadorOllama("gemma2:2b", transport=httpx.MockTransport(manejador))


def respuesta_ollama(contenido) -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": contenido}})


def test_ollama_respuesta_valida_y_peticion_bien_formada():
    peticiones = []

    def manejador(p):
        peticiones.append(json.loads(p.content))
        return respuesta_ollama('{"valor": "lítico", "confianza": 0.9, "justificacion": "piedra"}')

    r = ollama_con(manejador).proponer("sistema", "mensaje", ["lítico", "otro"])
    assert r.valor == "lítico" and r.confianza == 0.9
    cuerpo = peticiones[0]
    assert cuerpo["model"] == "gemma2:2b" and cuerpo["options"]["temperature"] == 0
    assert cuerpo["format"]["properties"]["valor"]["enum"] == ["lítico", "otro"]


@pytest.mark.parametrize(
    "contenido",
    ["no es json", '{"valor": "plástico", "confianza": 0.9, "justificacion": "x"}',
     '{"valor": "lítico", "confianza": 1.7, "justificacion": "x"}'],
)  # fmt: skip
def test_ollama_respuesta_invalida(contenido):
    with pytest.raises(RespuestaInvalida):
        ollama_con(lambda _: respuesta_ollama(contenido)).proponer("s", "m", ["lítico", "otro"])


def test_ollama_no_disponible():
    with pytest.raises(ModeloNoDisponible, match="ollama pull"):
        ollama_con(lambda _: httpx.Response(404)).proponer("s", "m", ["otro"])

    def caido(_):
        raise httpx.ConnectError("conexión rechazada")

    with pytest.raises(ModeloNoDisponible, match="conectar"):
        ollama_con(caido).proponer("s", "m", ["otro"])


def test_reintenta_una_vez_y_luego_manda_a_revision():
    intentos = iter(
        [RespuestaInvalida("x"), RespuestaLLM(valor="óseo", confianza=0.8, justificacion="hueso")]
    )

    def responder(_m, _c):
        r = next(intentos)
        if isinstance(r, Exception):
            raise r
        return r

    c = caso("material", "hueso de ballena", origen="descripcion", descripcion="hueso de ballena")
    propuesta, tiempos, invalida = consultar_llm(NormalizadorFalso(responder), PROMPT, c, VOCAB)
    assert (propuesta.valor, propuesta.metodo, propuesta.modelo, invalida) == (
        "óseo",
        "llm",
        "falso:1b",
        False,
    )
    assert len(tiempos) == 2

    def siempre_mal(_m, _c):
        raise RespuestaInvalida("basura")

    propuesta, tiempos, invalida = consultar_llm(NormalizadorFalso(siempre_mal), PROMPT, c, VOCAB)
    assert (propuesta.valor, propuesta.confianza, invalida, len(tiempos)) == ("otro", 0.0, True, 2)


# --- Proceso contra la base ---

FICHAS = ["16-447", "16-872", "16-919", "16-924", "16-1771", "16-3366"]


@pytest.fixture
def bd_con_fichas(bd):
    museo = db.obtener_museo_id(bd, 16)
    for i in FICHAS:
        db.guardar_ficha(bd, parsear_ficha(html_ficha(i), i), f"u/{i}", museo)
    return bd


def test_casos_incluyen_descripcion_cuando_falta_el_dato(bd_con_fichas):
    casos = {(c.surdoc_id, c.campo, c.orden): c for c in construir_casos(bd_con_fichas)}
    assert casos[("16-1771", "material", 0)].origen == "descripcion"  # sin Técnica / Material
    assert casos[("16-447", "material", 1)].origen == "termino"
    assert casos[("16-447", "tecnica", 1)].entrada == "Ahuecar"
    assert casos[("16-924", "estado_conservacion", 0)].origen == "campo"


def test_normalizacion_completa_incremental_y_trazable(bd_con_fichas):
    bd = bd_con_fichas
    falso = NormalizadorFalso(siempre("óseo", 0.7))
    r = ejecutar_normalizacion(bd, VOCAB, PROMPT, falso)
    assert r.sin_resolver == 0 and r.respuestas_invalidas == 0
    assert r.por_metodo["llm"] == len(falso.llamadas) > 0
    assert r.por_metodo["regla_id"] > 0 and r.por_metodo["sinonimo"] > 0

    fila = bd.execute(
        "select valor_normalizado, metodo, modelo, version_prompt, origen, confianza::float "
        "from normalizaciones "
        "where surdoc_id = '16-1771' and campo = 'material'"
    ).fetchone()
    assert fila == ("óseo", "llm", "falso:1b", "v1", "descripcion", 0.7)
    regla = bd.execute(
        "select valor_normalizado, metodo, modelo, entrada from normalizaciones "
        "where surdoc_id = '16-447' and campo = 'objeto'"
    ).fetchone()
    assert regla == ("embarcación", "regla_id", None, "Canoa monóxila")
    conflicto = bd.execute(
        "select confianza::float from normalizaciones "
        "where surdoc_id = '16-872' and campo = 'material'"
    ).fetchone()[0]
    assert conflicto == 0.5

    ejecucion = bd.execute(
        "select tipo_proceso, registros_procesados, detalle->>'llamadas_llm', "
        "detalle->>'version_prompt' "
        "from ejecuciones order by id desc limit 1"
    ).fetchone()
    assert ejecucion == ("normalizacion", r.guardados, str(len(falso.llamadas)), "v1")

    # Segunda corrida: nada pendiente.
    otra = NormalizadorFalso(siempre("lítico"))
    assert ejecutar_normalizacion(bd, VOCAB, PROMPT, otra).pendientes == 0 and not otra.llamadas

    # Si la ficha cambia en SURDOC, sus valores vuelven a quedar pendientes.
    cambiada = html_ficha("16-924").replace(">Regular<", ">Bueno<", 1)
    db.guardar_ficha(bd, parsear_ficha(cambiada, "16-924"), "u", db.obtener_museo_id(bd, 16))
    pendientes = filtrar_pendientes(bd, construir_casos(bd), "v1")
    assert {c.surdoc_id for c in pendientes} == {"16-924"}


def test_una_version_nueva_de_prompt_no_borra_la_anterior_ni_las_revisiones(bd_con_fichas):
    bd = bd_con_fichas
    ejecutar_normalizacion(bd, VOCAB, PROMPT, NormalizadorFalso(siempre("óseo")))
    bd.execute(
        "insert into revisiones (surdoc_id, campo, orden, valor_anterior, valor_corregido, "
        "revisado_por) "
        "values ('16-1771', 'material', 0, 'óseo', 'óseo', gen_random_uuid())"
    )
    v2 = Prompt("v2", PROMPT.plantilla)
    ejecutar_normalizacion(bd, VOCAB, v2, NormalizadorFalso(siempre("lítico")))
    versiones = bd.execute(
        "select version_prompt, valor_normalizado from normalizaciones "
        "where surdoc_id = '16-1771' and campo = 'material' order by 1"
    ).fetchall()
    assert versiones == [("v1", "óseo"), ("v2", "lítico")]
    assert bd.execute("select count(*) from revisiones").fetchone()[0] == 1


def test_sin_llm_deja_pendiente_lo_que_requiere_modelo(bd_con_fichas):
    r = ejecutar_normalizacion(bd_con_fichas, VOCAB, PROMPT, None)
    assert r.sin_resolver > 0 and "llm" not in r.por_metodo
    assert r.pendientes == r.guardados + r.sin_resolver


def test_modelo_caido_detiene_la_corrida_y_guarda_lo_avanzado(bd_con_fichas):
    def caido(_m, _c):
        raise ModeloNoDisponible("PC apagado")

    with pytest.raises(ModeloNoDisponible):
        ejecutar_normalizacion(bd_con_fichas, VOCAB, PROMPT, NormalizadorFalso(caido))
    errores = bd_con_fichas.execute(
        "select errores, fin is not null from ejecuciones order by id desc limit 1"
    ).fetchone()
    assert errores == (1, True)


# --- Calidad ---


def test_metricas_y_umbral_calibrado():
    filas = (
        [FilaRevisada("regla_id", 0.99, True)] * 20
        + [FilaRevisada("llm", 0.9, True)] * 8 + [FilaRevisada("llm", 0.9, False)] * 2
        + [FilaRevisada("llm", 0.6, False)] * 5
    )  # fmt: skip
    m = calcular_metricas(filas, objetivo=0.9)
    assert m["por_metodo"]["regla_id"]["precision"] == 1.0
    assert m["por_metodo"]["llm"]["precision"] == pytest.approx(8 / 15)
    assert m["umbral_recomendado"] == 0.65  # sobre 0,6 quedan 28 aciertos de 30
    assert "Umbral recomendado" in informe_markdown(m)


def test_muestra_reproducible_y_lectura_de_la_revision(bd_con_fichas, tmp_path):
    ejecutar_normalizacion(bd_con_fichas, VOCAB, PROMPT, NormalizadorFalso(siempre("lítico", 0.6)))
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    n = exportar_muestra(bd_con_fichas, "material", 5, "v1", 7, a)
    exportar_muestra(bd_con_fichas, "material", 5, "v1", 7, b)
    assert n == 5 and a.read_text(encoding="utf-8-sig") == b.read_text(encoding="utf-8-sig")
    with open(a, encoding="utf-8-sig") as archivo:
        filas = list(csv.DictReader(archivo))
    filas[0]["valor_correcto"] = filas[0]["valor_propuesto"].upper()  # mayúsculas: igual acierta
    filas[1]["valor_correcto"] = "cerámica"
    with open(a, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=filas[0].keys())
        escritor.writeheader()
        escritor.writerows(filas)
    revisadas = leer_revision([a])
    assert len(revisadas) == 2 and revisadas[0].acierto
    assert revisadas[1].acierto is (filas[1]["valor_propuesto"] == "cerámica")
