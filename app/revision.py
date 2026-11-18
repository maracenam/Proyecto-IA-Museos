"""Revisión humana: solo una revisora autenticada puede guardar.

- Cola de revisión: valores dudosos (confianza baja, "otro" o conflicto con la descripción).
- Muestra de calidad: valores elegidos al azar para medir la precisión del sistema. Cada valor
  pide una decisión explícita (no viene nada marcado) y no se muestran la confianza ni el método,
  para no influir en la respuesta.

La sesión se inicia con Supabase Auth y cada respuesta viaja con el token de la revisora; la
base (RLS) comprueba que su usuario esté en `revisores`. Sin sesión no hay forma de escribir."""

import streamlit as st

from comun import fuente, leer, pie, refrescar
from datos import ErrorEscritura, ErrorSesion
from logica import NOMBRES_CAMPO, NOMBRES_METODO, coma

POR_PAGINA = 10

st.title("Revisión")

sesion = st.session_state.get("sesion")

if sesion is None:
    st.markdown(
        "Aquí una persona valida lo que propuso el sistema. Cada decisión queda firmada con su "
        "usuario y **prevalece sobre cualquier versión futura del modelo**."
    )
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
# Texto plano: en markdown, Streamlit convierte los correos en enlaces mailto.
arriba[0].text(f"Sesión iniciada como {sesion.correo}")
if arriba[1].button("Cerrar sesión"):
    st.session_state.pop("sesion")
    st.rerun()

categorias: dict[str, list[str]] = {}
for c in leer("categorias"):
    categorias.setdefault(c["campo"], []).append(c["categoria"])


def nombre_campo(campo: str) -> str:
    return NOMBRES_CAMPO.get(campo, campo)


def contexto_ficha(item: dict) -> None:
    """Descripción, valor declarado, enlace y foto de la ficha (común a ambas pestañas)."""
    texto, imagen = st.columns([3, 1])
    with texto:
        st.markdown(f"**{item['objeto'] or 'Sin objeto'}** · `{item['surdoc_id']}`")
        st.write(item["descripcion"] or "Sin descripción.")
        declarado = (
            "no lo declara (se infirió de la descripción)"
            if item["origen"] == "descripcion"
            else f"«{item['entrada']}»"
        )
        st.markdown(
            f"**{nombre_campo(item['campo'])} declarado en SURDOC:** {declarado}  \n"
            f"**Técnica / Material en la ficha:** {item['tecnica_material'] or '—'}  \n"
            f"[Ver ficha en SURDOC]({item['url_ficha']})"
        )
    with imagen:
        if item.get("url_imagen"):
            st.image(item["url_imagen"], caption=item.get("credito_imagen") or None)


def clave_de(m: dict) -> str:
    return f"{m['surdoc_id']}|{m['campo']}|{m['orden']}|{m['version_prompt']}"


def guardar(accion, mensaje: str) -> None:
    try:
        accion()
    except ErrorEscritura as error:
        st.error(str(error))
        return
    refrescar()
    st.toast(mensaje)
    st.rerun()


# --- Pestaña: muestra de calidad ---


def mostrar_muestra() -> None:
    st.markdown(
        "Valores elegidos **al azar** para medir cuánto acierta el sistema. Para cada uno, indica "
        "si la categoría propuesta es correcta o elige la correcta. Con esto se publica la "
        "precisión por método y se calibra el umbral de revisión."
    )
    muestra = leer("muestra_calidad_detalle")
    if not muestra:
        st.info(
            "Todavía no hay una muestra creada. Se crea con "
            "`python -m pipeline.normalize muestra --campo material` (y `--campo objeto`)."
        )
        return

    campos = sorted({m["campo"] for m in muestra}, key=list(NOMBRES_CAMPO).index)
    campo = st.radio("Campo", campos, format_func=nombre_campo, horizontal=True, key="m_campo")
    del_campo = sorted((m for m in muestra if m["campo"] == campo), key=lambda m: m["posicion"])
    revisados = [m for m in del_campo if m["valor_correcto"] is not None]
    st.progress(
        len(revisados) / len(del_campo),
        text=f"{len(revisados)} de {len(del_campo)} revisados",
    )

    saltados: set[str] = st.session_state.setdefault("m_saltados", set())
    pendientes = [m for m in del_campo if m["valor_correcto"] is None]
    siguientes = [m for m in pendientes if clave_de(m) not in saltados]

    if not pendientes:
        st.success(f"Muestra de {nombre_campo(campo).lower()} completa. ¡Gracias!")
    elif not siguientes:
        st.info(f"Saltaste los {len(pendientes)} valores que quedan.")
        if st.button("Volver a los saltados"):
            saltados.clear()
            st.rerun()
    else:
        item = siguientes[0]
        clave = clave_de(item)
        with st.container(border=True):
            st.caption(f"Valor {item['posicion']} de {len(del_campo)} · {nombre_campo(campo)}")
            contexto_ficha(item)
            st.markdown(f"### El sistema propone: **{item['valor_propuesto']}**")
            correcto, otra, saltar = st.columns([2, 3, 1.2], vertical_alignment="bottom")
            if correcto.button(
                f"Correcto: {item['valor_propuesto']}", type="primary", key=f"ok|{clave}",
                use_container_width=True,
            ):  # fmt: skip
                guardar(
                    lambda: fuente().responder_muestra(
                        sesion,
                        item["surdoc_id"],
                        item["campo"],
                        item["orden"],
                        item["version_prompt"],
                        item["valor_propuesto"],
                    ),  # fmt: skip
                    f"Correcto: {item['surdoc_id']} → {item['valor_propuesto']}",
                )
            opciones = [c for c in categorias.get(campo, []) if c != item["valor_propuesto"]]
            with otra:
                elegida = st.selectbox(
                    "No es correcto, es:", opciones, index=None,
                    placeholder="Elige la categoría correcta", key=f"otra|{clave}",
                )  # fmt: skip
                if st.button(
                    "Guardar corrección", key=f"corr|{clave}", disabled=elegida is None,
                    use_container_width=True,
                ):  # fmt: skip
                    guardar(
                        lambda: fuente().responder_muestra(
                            sesion,
                            item["surdoc_id"],
                            item["campo"],
                            item["orden"],
                            item["version_prompt"],
                            elegida,
                        ),  # fmt: skip
                        f"Corregido: {item['surdoc_id']} → {elegida}",
                    )
            if saltar.button("Saltar", key=f"saltar|{clave}", use_container_width=True):
                saltados.add(clave)
                st.rerun()
        st.caption(
            "Si dudas entre dos categorías, elige la que describe mejor el material o tipo "
            "principal de la pieza; el comentario se puede discutir después con la arqueóloga."
        )

    if revisados:
        with st.expander(f"Respuestas dadas ({len(revisados)})"):
            st.dataframe(
                [
                    {
                        "Registro": m["surdoc_id"],
                        "Objeto": m["objeto"],
                        "Propuesta": m["valor_propuesto"],
                        "Respuesta": m["valor_correcto"],
                        "Acierto": "Sí" if m["valor_correcto"] == m["valor_propuesto"] else "No",
                    }
                    for m in revisados
                ],
                hide_index=True,
                use_container_width=True,
            )
            st.caption("Para cambiar una respuesta, corrígela en la página Colección o en la cola.")


# --- Pestaña: cola de revisión ---


def motivo(item: dict) -> str:
    """Por qué un valor está en la cola, en palabras de quien revisa."""
    if item["valor_propuesto"] == "otro":
        return "El sistema no encontró una categoría que calce."
    if "La descripción sugiere" in (item["justificacion"] or ""):
        sugerida = item["justificacion"].split("La descripción sugiere", 1)[1].split(":")[0].strip()
        return f"Lo declarado en SURDOC no calza con la descripción, que sugiere {sugerida}."
    return f"Confianza baja ({coma(item['confianza'])})."


def mostrar_cola() -> None:
    st.markdown(
        "Valores con confianza baja, sin categoría o que contradicen la descripción de la ficha."
    )
    cola = leer("cola_revision")
    if not cola:
        st.success("No quedan valores pendientes de revisión.")
        return
    imagenes = {
        f["surdoc_id"]: (f["url_imagen"], f["credito_imagen"]) for f in leer("fichas_publicas")
    }
    campos = sorted({c["campo"] for c in cola}, key=list(NOMBRES_CAMPO).index)
    elegidos = st.multiselect(
        "Campos", campos, default=campos, format_func=nombre_campo, key="r_campos"
    )
    pendientes = sorted(
        (c for c in cola if c["campo"] in elegidos),
        key=lambda c: (c["metodo"] != "llm" or c["confianza"] > 0, c["confianza"]),
    )
    paginas = max(1, -(-len(pendientes) // POR_PAGINA))
    st.caption(f"{len(pendientes)} valores pendientes")
    pagina = (
        st.number_input("Página", 1, paginas, 1, key="r_pagina") if paginas > 1 else 1
    )  # fmt: skip

    for item in pendientes[(pagina - 1) * POR_PAGINA : pagina * POR_PAGINA]:
        clave = f"{item['surdoc_id']}|{item['campo']}|{item['orden']}"
        url, credito = imagenes.get(item["surdoc_id"], (None, None))
        with st.container(border=True):
            st.caption(nombre_campo(item["campo"]))
            contexto_ficha({**item, "url_imagen": url, "credito_imagen": credito})
            metodo = NOMBRES_METODO.get(item["metodo"], item["metodo"])
            if item["modelo"]:
                metodo += f" · {item['modelo']}"
            st.markdown(f"### El sistema propone: **{item['valor_propuesto']}**")
            st.caption(f"{motivo(item)} Propuesto por: {metodo}.")
            opciones = categorias.get(item["campo"], [item["valor_propuesto"]])
            inicial = (
                opciones.index(item["valor_propuesto"])
                if item["valor_propuesto"] in opciones
                else 0
            )
            seleccion, boton = st.columns([3, 1], vertical_alignment="bottom")
            valor = seleccion.selectbox(
                "Valor correcto", opciones, index=inicial, key=f"sel|{clave}"
            )
            if boton.button(
                "Guardar revisión", key=f"btn|{clave}", type="primary", use_container_width=True
            ):
                guardar(
                    lambda item=item, valor=valor: fuente().guardar_revision(
                        sesion,
                        item["surdoc_id"],
                        item["campo"],
                        item["orden"],
                        item["valor_propuesto"],
                        valor,
                    ),  # fmt: skip
                    f"Revisión guardada: {item['surdoc_id']} → {valor}",
                )


pestana_muestra, pestana_cola = st.tabs(["Muestra de calidad", "Cola de revisión"])
with pestana_muestra:
    mostrar_muestra()
with pestana_cola:
    mostrar_cola()

pie()
