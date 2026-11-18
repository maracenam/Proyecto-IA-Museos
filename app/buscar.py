"""Página pública: búsqueda en lenguaje natural (Sprint 4)."""

import streamlit as st

from busqueda import MODELO_POR_DEFECTO, vector_consulta
from comun import fuente, leer, pie
from datos import leer_config
from logica import ESTADOS

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

if "consulta" not in st.session_state:
    st.session_state["consulta"] = ""

columnas = st.columns(len(EJEMPLOS))
for columna, ejemplo in zip(columnas, EJEMPLOS, strict=True):
    if columna.button(ejemplo, key=f"ej|{ejemplo}", use_container_width=True):
        st.session_state["consulta"] = ejemplo

with st.form("buscar"):
    consulta = st.text_input(
        "Consulta", key="consulta", placeholder="Ej.: herramientas de piedra para cazar"
    )
    st.form_submit_button("Buscar", type="primary")

if not consulta.strip():
    st.caption("Prueba con uno de los ejemplos de arriba.")
    pie()
    st.stop()

modelo = leer_config().get("EMBEDDING_MODELO") or MODELO_POR_DEFECTO
resultados = fuente().buscar(vector_consulta(consulta.strip(), modelo), modelo, RESULTADOS)

if not resultados:
    st.warning(
        "No hay fichas indexadas para la búsqueda todavía. Genera los embeddings con "
        "`python -m pipeline.embed generar`."
    )
    pie()
    st.stop()

fichas = {f["surdoc_id"]: f for f in leer("fichas_publicas")}
valores: dict[str, list[dict]] = {}
for v in leer("valor_vigente"):
    if v["campo"] in ("objeto", "material") and v["orden"] == 0:
        valores.setdefault(v["surdoc_id"], []).append(v)

st.caption(f"{len(resultados)} fichas más parecidas a «{consulta.strip()}»")
for posicion, r in enumerate(resultados, 1):
    ficha = fichas.get(r["surdoc_id"])
    if ficha is None:
        continue
    with st.container(border=True):
        texto, imagen = st.columns([4, 1])
        with texto:
            st.markdown(
                f"**{posicion}. {ficha['objeto'] or 'Sin objeto'}** · `{ficha['surdoc_id']}` · "
                f"parecido {r['similitud']:.2f}".replace(".", ",")
            )
            etiquetas = [
                f"{'Tipo' if v['campo'] == 'objeto' else 'Material'}: **{v['valor']}** "
                f"({ESTADOS[v['estado']].lower()})"
                for v in sorted(
                    valores.get(r["surdoc_id"], []), key=lambda v: v["campo"] != "objeto"
                )
            ]
            if etiquetas:
                st.markdown(" · ".join(etiquetas))
            descripcion = ficha["descripcion"] or "Sin descripción."
            st.write(descripcion[:300] + ("…" if len(descripcion) > 300 else ""))
            st.markdown(f"[Ver ficha en SURDOC]({ficha['url_ficha']})")
        with imagen:
            if ficha["url_imagen"]:
                st.image(ficha["url_imagen"], caption=ficha["credito_imagen"] or None)

st.caption(
    "El parecido va de 0 a 1 y es relativo: sirve para ordenar, no como medida absoluta. "
    "Los 10 casos de prueba del proyecto encuentran al menos una ficha pertinente entre los "
    "5 primeros resultados."
)
pie()
