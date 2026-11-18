"""Página pública: búsqueda en lenguaje natural (Sprint 4)."""

import logging

import streamlit as st

from busqueda import MODELO_POR_DEFECTO, vector_consulta
from comun import fuente, leer, pie
from datos import leer_config
from logica import ESTADOS, coma

log = logging.getLogger(__name__)

EJEMPLOS = [
    "instrumento de piedra para raspar cueros",
    "cestería tejida con fibras vegetales",
    "piezas de hueso de ballena para pescar",
    "embarcación de los pueblos canoeros",
    "adornos de metal",
]
RESULTADOS = 10

st.title("Buscar en la colección")
st.markdown(
    "Escribe lo que buscas con tus palabras, sin conocer la terminología exacta. La búsqueda "
    "compara el significado de tu consulta con el de cada ficha, usando un modelo de lenguaje "
    "abierto."
)

st.session_state.setdefault("consulta", "")


def usar_ejemplo() -> None:
    elegido = st.session_state.get("ejemplo")
    if elegido:
        st.session_state["consulta"] = elegido


with st.form("buscar", border=False):
    entrada, boton = st.columns([5, 1], vertical_alignment="bottom")
    consulta = entrada.text_input(
        "¿Qué buscas?", key="consulta", placeholder="Ej.: herramientas de piedra para cazar"
    )
    boton.form_submit_button("Buscar", type="primary", use_container_width=True)
st.pills("O prueba un ejemplo", EJEMPLOS, key="ejemplo", on_change=usar_ejemplo)

consulta = consulta.strip()
if not consulta:
    pie()
    st.stop()

modelo = leer_config().get("EMBEDDING_MODELO") or MODELO_POR_DEFECTO
try:
    resultados = fuente().buscar(vector_consulta(consulta, modelo), modelo, RESULTADOS)
except Exception:
    log.exception("Falló la búsqueda")
    st.error(
        "La búsqueda no está disponible en este momento. Intenta de nuevo en unos minutos; "
        "mientras tanto puedes filtrar las fichas en la página Colección."
    )
    pie()
    st.stop()

if not resultados:
    st.info(
        "La búsqueda todavía no tiene fichas indexadas. Aparecerán después de generar los "
        "embeddings (`python -m pipeline.embed generar`)."
    )
    pie()
    st.stop()

fichas = {f["surdoc_id"]: f for f in leer("fichas_publicas")}
valores: dict[str, list[dict]] = {}
for v in leer("valor_vigente"):
    if v["campo"] in ("objeto", "material") and v["orden"] == 0:
        valores.setdefault(v["surdoc_id"], []).append(v)


def etiqueta(v: dict) -> str:
    campo = "Tipo" if v["campo"] == "objeto" else "Material"
    valor = "sin categoría" if v["valor"] == "otro" else v["valor"]
    return f"{campo}: **{valor}** ({ESTADOS[v['estado']].lower()})"


st.caption(f"Las {len(resultados)} fichas más parecidas a «{consulta}»")
for posicion, r in enumerate(resultados, 1):
    ficha = fichas.get(r["surdoc_id"])
    if ficha is None:
        continue
    with st.container(border=True):
        texto, imagen = st.columns([4, 1], gap="medium")
        with texto:
            st.markdown(
                f"**{posicion}. {ficha['objeto'] or 'Sin objeto'}** · `{ficha['surdoc_id']}`"
            )
            propias = sorted(valores.get(r["surdoc_id"], []), key=lambda v: v["campo"] != "objeto")
            if propias:
                st.markdown(" · ".join(etiqueta(v) for v in propias))
            descripcion = ficha["descripcion"] or "Sin descripción en SURDOC."
            st.write(descripcion[:300] + ("…" if len(descripcion) > 300 else ""))
            st.markdown(
                f"[Ver ficha en SURDOC]({ficha['url_ficha']}) · "
                f"<span style='color:#5b6b75'>parecido {coma(r['similitud'])}</span>",
                unsafe_allow_html=True,
            )
        with imagen:
            if ficha["url_imagen"]:
                st.image(ficha["url_imagen"], caption=ficha["credito_imagen"] or None)

st.caption(
    "El parecido va de 0 a 1 y sirve para ordenar, no como medida absoluta. En las 10 consultas "
    "de prueba del proyecto, al menos una ficha pertinente aparece entre los 5 primeros resultados."
)
pie()
