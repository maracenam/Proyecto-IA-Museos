"""Cola de revisión: solo una revisora autenticada puede guardar correcciones.

La sesión se inicia con Supabase Auth y la corrección viaja con el token de la revisora; la
base (RLS) comprueba que su usuario esté en `revisores`. Sin sesión no hay forma de escribir."""

import streamlit as st

from comun import fuente, leer, pie, refrescar
from datos import ErrorEscritura, ErrorSesion
from logica import NOMBRES_CAMPO

POR_PAGINA = 10

st.title("Cola de revisión")
st.markdown(
    "Valores con confianza baja o que contradicen la descripción de la ficha. Una corrección "
    "queda firmada con tu usuario y **prevalece sobre cualquier versión futura del modelo**."
)

sesion = st.session_state.get("sesion")

if sesion is None:
    with st.form("inicio_sesion"):
        st.subheader("Iniciar sesión")
        correo = st.text_input("Correo", key="correo")
        clave = st.text_input("Contraseña", type="password", key="clave")
        enviado = st.form_submit_button("Entrar", type="primary")
    if enviado:
        try:
            st.session_state["sesion"] = fuente().iniciar_sesion(correo.strip(), clave)
            st.rerun()
        except ErrorSesion as error:
            st.error(str(error))
    st.caption("Solo personas registradas como revisoras pueden entrar. La exploración es pública.")
    pie()
    st.stop()

arriba = st.columns([4, 1])
arriba[0].caption(f"Sesión iniciada como {sesion.correo}")
if arriba[1].button("Cerrar sesión"):
    st.session_state.pop("sesion")
    st.rerun()

cola = leer("cola_revision")
categorias = {}
for c in leer("categorias"):
    categorias.setdefault(c["campo"], []).append(c["categoria"])

if not cola:
    st.success("No hay valores pendientes de revisión.")
    pie()
    st.stop()

campos = sorted({c["campo"] for c in cola}, key=list(NOMBRES_CAMPO).index)
elegidos = st.multiselect(
    "Campos", campos, default=campos, format_func=lambda c: NOMBRES_CAMPO.get(c, c), key="r_campos"
)
pendientes = sorted(
    (c for c in cola if c["campo"] in elegidos),
    key=lambda c: (c["metodo"] != "llm" or c["confianza"] > 0, c["confianza"]),
)
st.caption(f"{len(pendientes)} valores pendientes")
pagina = st.number_input(
    "Página", 1, max(1, -(-len(pendientes) // POR_PAGINA)), 1, key="r_pagina"
)  # fmt: skip

for item in pendientes[(pagina - 1) * POR_PAGINA : pagina * POR_PAGINA]:
    clave = f"{item['surdoc_id']}|{item['campo']}|{item['orden']}"
    with st.container(border=True):
        izquierda, derecha = st.columns([3, 2])
        with izquierda:
            st.markdown(
                f"**{item['objeto'] or 'Sin objeto'}** · `{item['surdoc_id']}` · "
                f"{NOMBRES_CAMPO.get(item['campo'], item['campo'])}"
            )
            st.write(item["descripcion"] or "Sin descripción.")
            st.markdown(f"[Ver ficha en SURDOC]({item['url_ficha']})")
        with derecha:
            origen = (
                "inferido de la descripción" if item["origen"] == "descripcion" else item["entrada"]
            )
            st.markdown(
                f"**Declarado:** {origen}  \n"
                f"**Propuesta:** {item['valor_propuesto']} · confianza {item['confianza']:.2f}  \n"
                f"**Método:** {item['metodo']}" + (f" ({item['modelo']})" if item["modelo"] else "")
            )
            st.caption(item["justificacion"] or "")
            opciones = categorias.get(item["campo"], [item["valor_propuesto"]])
            inicial = (
                opciones.index(item["valor_propuesto"])
                if item["valor_propuesto"] in opciones
                else 0
            )
            valor = st.selectbox("Valor correcto", opciones, index=inicial, key=f"sel|{clave}")
            if st.button("Guardar revisión", key=f"btn|{clave}", type="primary"):
                try:
                    fuente().guardar_revision(
                        sesion, item["surdoc_id"], item["campo"], item["orden"],
                        item["valor_propuesto"], valor,
                    )  # fmt: skip
                    refrescar()
                    st.toast(f"Revisión guardada: {item['surdoc_id']} → {valor}")
                    st.rerun()
                except ErrorEscritura as error:
                    st.error(str(error))

pie()
