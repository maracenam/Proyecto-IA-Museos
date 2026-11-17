"""Pruebas de la app (Sprint 3): datos, lógica, seguridad de escritura y valor vigente."""

import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest

from pipeline import db
from pipeline.normalize.llm import Prompt, RespuestaLLM
from pipeline.normalize.proceso import ejecutar_normalizacion
from pipeline.normalize.vocabulario import Vocabulario, sincronizar_vocabulario
from pipeline.parse.ficha import parsear_ficha
from tests.conftest import html_ficha

DIRECTORIO_APP = Path(__file__).parents[1] / "app"
sys.path.insert(0, str(DIRECTORIO_APP))

from datos import ErrorEscritura, ErrorSesion, FuentePostgres, FuenteSupabase, Sesion, crear_fuente  # noqa: E402
from logica import conteo_por_estado, filtrar, indicadores, tabla_fichas, valores_de_ficha  # noqa: E402

VOCAB = Vocabulario.cargar()
FICHAS = ["16-447", "16-872", "16-919", "16-924", "16-1771", "16-3366"]


class NormalizadorFijo:
    def __init__(self, valor, confianza=0.9, modelo="falso:1b"):
        self.valor, self.confianza, self.modelo = valor, confianza, modelo

    def proponer(self, sistema, mensaje, categorias):
        valor = self.valor if self.valor in categorias else "otro"
        return RespuestaLLM(valor=valor, confianza=self.confianza, justificacion="prueba")


@pytest.fixture
def bd_app(bd):
    museo = db.obtener_museo_id(bd, 16)
    for i in FICHAS:
        db.guardar_ficha(bd, parsear_ficha(html_ficha(i), i), f"u/{i}", museo)
    sincronizar_vocabulario(bd, VOCAB)
    ejecutar_normalizacion(bd, VOCAB, Prompt.cargar("v1"), NormalizadorFijo("óseo", 0.6))
    return bd


def revisora(bd) -> Sesion:
    uid = str(uuid.uuid4())
    bd.execute("insert into revisores (usuario_id, nombre) values (%s, 'Revisora')", (uid,))
    return Sesion(uid, "revisora@ejemplo.cl", "local")


def vigente(bd, surdoc_id, campo):
    return bd.execute(
        "select valor, estado from valor_vigente where surdoc_id = %s and campo = %s and orden = 0",
        (surdoc_id, campo),
    ).fetchone()


# --- Lectura pública ---


def test_lectura_publica_sin_datos_sensibles(bd_app):
    fuente = FuentePostgres(con=bd_app)
    fichas = fuente.leer("fichas_publicas")
    assert {f["surdoc_id"] for f in fichas} == set(FICHAS)
    assert all("nombre_sitio" not in f for f in fichas)
    assert all(f["url_ficha"].startswith("https://www.surdoc.cl/registro/") for f in fichas)
    with pytest.raises(ValueError):
        fuente.leer("registros_raw")  # solo vistas públicas


def test_valor_vigente_marca_lo_dudoso_para_revision(bd_app):
    assert vigente(bd_app, "16-447", "objeto") == ("embarcación", "propuesto")  # regla por ID
    assert vigente(bd_app, "16-872", "material") == ("madera", "en_revision")  # conflicto 0,5
    assert vigente(bd_app, "16-1771", "material") == ("óseo", "en_revision")  # LLM 0,6 < 0,8
    cola = {(c["surdoc_id"], c["campo"]) for c in FuentePostgres(con=bd_app).leer("cola_revision")}
    assert ("16-872", "material") in cola and ("16-447", "objeto") not in cola


# --- Escritura protegida ---


def test_sin_revisor_registrado_no_se_puede_escribir(bd_app):
    intrusa = Sesion(str(uuid.uuid4()), "x@ejemplo.cl", "local")
    with pytest.raises(ErrorEscritura, match="autorizado"):
        FuentePostgres(con=bd_app).guardar_revision(
            intrusa, "16-872", "material", 0, "madera", "cerámica"
        )
    assert bd_app.execute("select count(*) from revisiones").fetchone()[0] == 0


def test_anon_no_puede_insertar_revisiones(bd_app):
    import psycopg

    with pytest.raises(psycopg.errors.InsufficientPrivilege), bd_app.transaction():
        bd_app.execute("set local role anon")
        bd_app.execute(
            "insert into revisiones (surdoc_id, campo, orden, valor_corregido, revisado_por) "
            "values ('16-872', 'material', 0, 'cerámica', gen_random_uuid())"
        )


def test_categoria_invalida_es_rechazada(bd_app):
    with pytest.raises(ErrorEscritura, match="categoría válida"):
        FuentePostgres(con=bd_app).guardar_revision(
            revisora(bd_app), "16-872", "material", 0, "madera", "plástico"
        )


def test_revision_firma_con_el_usuario_y_sobrevive_a_un_prompt_nuevo(bd_app):
    sesion = revisora(bd_app)
    FuentePostgres(con=bd_app).guardar_revision(
        sesion, "16-872", "material", 0, "madera", "cerámica"
    )
    assert vigente(bd_app, "16-872", "material") == ("cerámica", "revisado")
    firmado = bd_app.execute("select revisado_por::text from revisiones").fetchone()[0]
    assert firmado == sesion.usuario_id
    # Criterio del Sprint 3: un prompt nuevo no pisa la revisión humana.
    ejecutar_normalizacion(
        bd_app, VOCAB, Prompt("v2", Prompt.cargar("v1").plantilla), NormalizadorFijo("lítico", 0.95)
    )
    assert vigente(bd_app, "16-872", "material") == ("cerámica", "revisado")
    assert vigente(bd_app, "16-1771", "material") == (
        "lítico",
        "propuesto",
    )  # sin revisión: manda v2


def test_inicio_de_sesion_local_solo_para_la_revisora_configurada(bd_app):
    fuente = FuentePostgres(con=bd_app, correo_revisor="r@ejemplo.cl", id_revisor=str(uuid.uuid4()))
    assert fuente.iniciar_sesion("r@ejemplo.cl", "x").correo == "r@ejemplo.cl"
    with pytest.raises(ErrorSesion):
        fuente.iniciar_sesion("otra@ejemplo.cl", "x")


# --- Supabase (REST simulado) ---


def supabase_con(manejador) -> FuenteSupabase:
    return FuenteSupabase(
        "https://proyecto.supabase.co", "clave-anon", transport=httpx.MockTransport(manejador)
    )


def test_supabase_lee_con_clave_publica():
    vistas = []

    def manejador(p):
        vistas.append((p.url.path, p.headers["apikey"], p.headers["Authorization"]))
        return httpx.Response(200, json=[{"surdoc_id": "16-1"}])

    assert supabase_con(manejador).leer("fichas_publicas") == [{"surdoc_id": "16-1"}]
    assert vistas == [("/rest/v1/fichas_publicas", "clave-anon", "Bearer clave-anon")]


def test_supabase_inicio_de_sesion_y_revision_con_token_de_usuaria():
    peticiones = []

    def manejador(p):
        peticiones.append(p)
        if p.url.path == "/auth/v1/token":
            if json.loads(p.content)["password"] != "correcta":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200, json={"access_token": "jwt-usuaria", "user": {"id": "u1", "email": "r@x.cl"}}
            )
        return httpx.Response(201)

    fuente = supabase_con(manejador)
    with pytest.raises(ErrorSesion):
        fuente.iniciar_sesion("r@x.cl", "mala")
    sesion = fuente.iniciar_sesion("r@x.cl", "correcta")
    fuente.guardar_revision(sesion, "16-872", "material", 0, "madera", "cerámica")
    insercion = peticiones[-1]
    assert insercion.url.path == "/rest/v1/revisiones"
    assert insercion.headers["Authorization"] == "Bearer jwt-usuaria"
    assert "revisado_por" not in json.loads(insercion.content)  # lo pone la base: auth.uid()


@pytest.mark.parametrize(
    ("estado", "mensaje"), [(401, "autorizado"), (403, "autorizado"), (409, "válida")]
)
def test_supabase_rechazos_de_escritura(estado, mensaje):
    with pytest.raises(ErrorEscritura, match=mensaje):
        supabase_con(lambda _: httpx.Response(estado)).guardar_revision(
            Sesion("u", "r@x.cl", "t"), "16-1", "material", 0, None, "x"
        )


def test_crear_fuente_prefiere_supabase():
    assert isinstance(
        crear_fuente({"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "k"}),
        FuenteSupabase,
    )
    with pytest.raises(RuntimeError):
        crear_fuente({})


# --- Lógica ---


def test_tabla_indicadores_y_filtros(bd_app):
    fuente = FuentePostgres(con=bd_app)
    fichas, valores = fuente.leer("fichas_publicas"), fuente.leer("valor_vigente")
    df = tabla_fichas(fichas, valores)
    assert list(df["surdoc_id"]) == ["16-447", "16-872", "16-919", "16-924", "16-1771", "16-3366"]
    canoa = df.set_index("surdoc_id").loc["16-447"]
    assert (canoa["tipo"], canoa["tipo_estado"]) == ("embarcación", "Propuesto por el sistema")
    ind = indicadores(fichas, valores)
    assert ind["fichas"] == 6 and ind["valores"] == ind["propuestos"] + ind["en_revision"]
    assert len(filtrar(df, texto="canoa")) == 1
    assert set(filtrar(df, materiales=["madera"])["surdoc_id"]) == {"16-447", "16-872"}
    assert len(filtrar(df, validacion=["En revisión"])) >= 2
    assert conteo_por_estado(df, "material")["Fichas"].sum() == 6
    assert list(valores_de_ficha(valores, "16-447")["Campo"])[:1] == ["Tipo de objeto"]


def test_tabla_vacia_no_falla():
    assert tabla_fichas([], []).empty


# --- La app arranca y muestra datos (Streamlit AppTest) ---


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="requiere Postgres local")
@pytest.mark.parametrize("pagina", ["inicio.py", "revision.py", "acerca.py"])
def test_paginas_cargan_sin_errores(pagina, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.chdir(DIRECTORIO_APP)
    prueba = AppTest.from_file(str(DIRECTORIO_APP / pagina), default_timeout=60).run()
    assert not prueba.exception, prueba.exception
    assert prueba.title  # cada página tiene título
