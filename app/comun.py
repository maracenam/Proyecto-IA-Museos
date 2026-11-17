"""Conexión y lectura con caché compartidas por las páginas."""

import streamlit as st

from datos import FuenteDatos, crear_fuente, leer_config


def _secretos() -> dict:
    try:
        return dict(st.secrets)
    except (FileNotFoundError, KeyError, st.errors.StreamlitSecretNotFoundError):
        return {}


@st.cache_resource
def fuente() -> FuenteDatos:
    return crear_fuente(leer_config(_secretos()))


@st.cache_data(ttl=300, show_spinner="Cargando datos…")
def leer(vista: str) -> list[dict]:
    return fuente().leer(vista)


def refrescar() -> None:
    leer.clear()


def pie() -> None:
    st.divider()
    st.caption(
        "Fuente: [SURDOC](https://www.surdoc.cl), Servicio Nacional del Patrimonio Cultural, y "
        "Museo Regional de Magallanes. Cada ficha enlaza a su registro original; las fotografías "
        "se muestran desde SURDOC con el crédito del fotógrafo. No se publican sitios "
        "arqueológicos ni ubicaciones exactas."
    )
