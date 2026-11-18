"""Muestra de calidad revisada desde la app (migración 008)."""

import sys
import uuid
from pathlib import Path

import pytest

from pipeline import db
from pipeline.normalize.calidad import calcular_metricas, crear_muestra, leer_muestra_revisada
from pipeline.normalize.llm import Prompt, RespuestaLLM
from pipeline.normalize.proceso import ejecutar_normalizacion
from pipeline.normalize.vocabulario import Vocabulario, sincronizar_vocabulario
from pipeline.parse.ficha import parsear_ficha
from tests.conftest import html_ficha

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))
from datos import ErrorEscritura, FuentePostgres, Sesion  # noqa: E402
from logica import metricas_muestra  # noqa: E402

FICHAS = ["16-447", "16-872", "16-919", "16-924", "16-989", "16-1771", "16-3366", "16-907"]
VOCAB = Vocabulario.cargar()


class NormalizadorFijo:
    modelo = "falso:1b"

    def proponer(self, sistema, mensaje, categorias):
        valor = "óseo" if "óseo" in categorias else "otro"
        return RespuestaLLM(valor=valor, confianza=0.6, justificacion="prueba")


@pytest.fixture
def bd_muestra(bd):
    museo = db.obtener_museo_id(bd, 16)
    for i in FICHAS:
        db.guardar_ficha(bd, parsear_ficha(html_ficha(i), i), f"u/{i}", museo)
    sincronizar_vocabulario(bd, VOCAB)
    ejecutar_normalizacion(bd, VOCAB, Prompt.cargar("v1"), NormalizadorFijo())
    return bd


def revisora(bd) -> Sesion:
    uid = str(uuid.uuid4())
    bd.execute("insert into revisores (usuario_id, nombre) values (%s, 'Revisora')", (uid,))
    return Sesion(uid, "r@ejemplo.cl", "local")


def orden_muestra(bd, campo="material"):
    return [
        f[0]
        for f in bd.execute(
            "select surdoc_id from muestra_calidad where campo = %s order by posicion", (campo,)
        )
    ]


def test_crear_muestra_reproducible_e_idempotente(bd_muestra):
    total, revisados = crear_muestra(bd_muestra, "material", 5, "v1", 2026)
    assert (total, revisados) == (5, 0)
    primero = orden_muestra(bd_muestra)
    bd_muestra.execute("delete from muestra_calidad")
    crear_muestra(bd_muestra, "material", 5, "v1", 2026)
    assert orden_muestra(bd_muestra) == primero  # misma semilla, mismo orden
    # Volver a correr no agrega ni cambia nada.
    assert crear_muestra(bd_muestra, "material", 50, "v1", 2026) == (5, 0)


def test_responder_correcto_y_corregir(bd_muestra):
    crear_muestra(bd_muestra, "material", 50, "v1", 2026)
    sesion = revisora(bd_muestra)
    fuente = FuentePostgres(con=bd_muestra)
    filas = {(m["surdoc_id"], m["orden"]): m for m in fuente.leer("muestra_calidad_detalle")}
    madera = filas[("16-872", 0)]  # fragmento cerámico registrado como madera
    assert madera["valor_propuesto"] == "madera" and madera["descripcion"]

    fuente.responder_muestra(sesion, "16-872", "material", 0, "v1", "cerámica")
    fuente.responder_muestra(sesion, "16-907", "material", 0, "v1", "madera")

    respuestas = dict(
        bd_muestra.execute(
            "select surdoc_id, valor_correcto from muestra_calidad where valor_correcto is not null"
        ).fetchall()
    )
    assert respuestas == {"16-872": "cerámica", "16-907": "madera"}
    firmadas = bd_muestra.execute(
        "select count(*) from muestra_calidad where revisado_por = %s", (sesion.usuario_id,)
    ).fetchone()[0]
    assert firmadas == 2
    # Toda respuesta queda también como revisión: el valor pasa a "revisado" en valor_vigente.
    vigentes = dict(
        bd_muestra.execute(
            "select surdoc_id, valor || '/' || estado from valor_vigente "
            "where campo = 'material' and orden = 0 and surdoc_id in ('16-872', '16-907')"
        ).fetchall()
    )
    assert vigentes == {"16-872": "cerámica/revisado", "16-907": "madera/revisado"}


def test_sin_permiso_no_se_responde(bd_muestra):
    import psycopg

    crear_muestra(bd_muestra, "material", 50, "v1", 2026)
    intrusa = Sesion(str(uuid.uuid4()), "x@ejemplo.cl", "local")
    with pytest.raises(ErrorEscritura, match="autorizado"):
        FuentePostgres(con=bd_muestra).responder_muestra(
            intrusa, "16-872", "material", 0, "v1", "cerámica"
        )
    with pytest.raises(psycopg.errors.InsufficientPrivilege), bd_muestra.transaction():
        bd_muestra.execute("set local role anon")
        bd_muestra.execute("select responder_muestra('16-872', 'material', 0, 'v1', 'cerámica')")
    with pytest.raises(psycopg.errors.InsufficientPrivilege), bd_muestra.transaction():
        bd_muestra.execute("set local role anon")
        bd_muestra.execute("update muestra_calidad set valor_correcto = 'cerámica'")
    assert (
        bd_muestra.execute("select count(valor_correcto) from muestra_calidad").fetchone()[0] == 0
    )


def test_categoria_invalida_y_valor_fuera_de_la_muestra(bd_muestra):
    crear_muestra(bd_muestra, "material", 50, "v1", 2026)
    sesion = revisora(bd_muestra)
    fuente = FuentePostgres(con=bd_muestra)
    with pytest.raises(ErrorEscritura, match="categoría válida"):
        fuente.responder_muestra(sesion, "16-872", "material", 0, "v1", "plástico")
    with pytest.raises(ErrorEscritura, match="no está en la muestra"):
        fuente.responder_muestra(sesion, "16-872", "material", 0, "v9", "cerámica")


def test_metricas_desde_la_base_y_en_la_app(bd_muestra):
    crear_muestra(bd_muestra, "material", 50, "v1", 2026)
    sesion = revisora(bd_muestra)
    fuente = FuentePostgres(con=bd_muestra)
    fuente.responder_muestra(sesion, "16-872", "material", 0, "v1", "cerámica")  # regla falla
    fuente.responder_muestra(sesion, "16-907", "material", 0, "v1", "madera")  # regla acierta
    fuente.responder_muestra(sesion, "16-1771", "material", 0, "v1", "óseo")  # LLM acierta

    m = calcular_metricas(leer_muestra_revisada(bd_muestra))
    assert m["revisados"] == 3 and m["aciertos"] == 2
    assert m["por_metodo"]["llm"]["precision"] == 1.0

    app = metricas_muestra(fuente.leer("muestra_calidad_detalle"))
    assert (app["revisados"], round(app["precision"], 2)) == (3, 0.67)
    por_metodo = app["por_metodo"].set_index("Método")
    assert por_metodo.loc["Vocabulario (ID)", "Aciertos"] == 1
    assert por_metodo.loc["IA local", "Precisión"] == 1.0


def test_metricas_muestra_umbral():
    filas = (
        [{"valor_propuesto": "a", "valor_correcto": "a", "metodo": "regla_id", "confianza": 0.99}]
        * 9
        + [{"valor_propuesto": "a", "valor_correcto": "b", "metodo": "llm", "confianza": 0.6}]
        + [{"valor_propuesto": "a", "valor_correcto": None, "metodo": "llm", "confianza": 0.7}]
    )  # fmt: skip
    m = metricas_muestra([dict(f) for f in filas], objetivo=0.95)
    assert (m["total"], m["revisados"], m["umbral_recomendado"]) == (11, 10, 0.65)
