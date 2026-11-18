"""Conexión, lectura con caché y piezas de interfaz compartidas por las páginas."""

import logging

import streamlit as st

from datos import FuenteDatos, crear_fuente, leer_config
from logica import DESCRIPCION_ESTADOS

log = logging.getLogger(__name__)

# Colores de validación: los mismos en gráficos, leyenda y tarjetas.
COLORES_ESTADO = {
    "Revisado": "#5d6f2c",
    "Propuesto": "#1f5f7a",
    "En revisión": "#b06a12",
    "Sin normalizar": "#8d99a1",
}


def _secretos() -> dict:
    try:
        return dict(st.secrets)
    except (FileNotFoundError, KeyError, st.errors.StreamlitSecretNotFoundError):
        return {}


@st.cache_resource
def fuente() -> FuenteDatos:
    return crear_fuente(leer_config(_secretos()))


@st.cache_data(ttl=300, show_spinner="Cargando datos…")
def _leer(vista: str) -> list[dict]:
    return fuente().leer(vista)


def leer(vista: str) -> list[dict]:
    """Lee una vista; si la base no responde, muestra un aviso con reintento en vez del error
    técnico y detiene la página."""
    try:
        return _leer(vista)
    except Exception:
        log.exception("No se pudo leer %s", vista)
        st.error(
            "No pudimos conectar con la base de datos en este momento. "
            "Suele resolverse en unos segundos."
        )
        if st.button("Reintentar", type="primary", key=f"reintentar|{vista}"):
            _leer.clear()
            st.rerun()
        st.stop()


def refrescar() -> None:
    _leer.clear()


def leyenda_validacion(estados: list[str] | None = None) -> None:
    """Leyenda única de los estados de validación (los gráficos no repiten la suya)."""
    estados = estados or list(COLORES_ESTADO)
    piezas = [
        f'<span style="display:inline-block;margin-right:1.1rem">'
        f'<span style="white-space:nowrap"><span style="display:inline-block;width:.7rem;'
        f"height:.7rem;border-radius:2px;background:{COLORES_ESTADO[e]};margin-right:.4rem;"
        f'vertical-align:-1px"></span><b>{e}</b></span> '
        f'<span style="color:#5b6b75">· {DESCRIPCION_ESTADOS[e]}</span></span>'
        for e in estados
    ]
    st.markdown(
        f'<div style="font-size:.86rem;line-height:1.9">{"".join(piezas)}</div>',
        unsafe_allow_html=True,
    )


def pie(enlace_guia: bool = True) -> None:
    st.divider()
    st.caption(
        "Fuente: [SURDOC](https://www.surdoc.cl), Servicio Nacional del Patrimonio Cultural, y "
        "Museo Regional de Magallanes. Cada ficha enlaza a su registro original; las fotografías "
        "se muestran desde SURDOC con el crédito del fotógrafo. No se publican sitios "
        "arqueológicos ni ubicaciones exactas."
    )
    if enlace_guia:
        try:
            st.page_link("guia.py", label="¿Cómo se usa? Ver la guía", icon=":material/help:")
        except st.errors.StreamlitPageNotFoundError:
            pass  # página ejecutada fuera de la navegación (pruebas)
