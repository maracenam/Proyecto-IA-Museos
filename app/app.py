"""Punto de entrada de la app: `streamlit run app/app.py`."""

import streamlit as st

st.set_page_config(
    page_title="Observatorio SURDOC",
    page_icon=":material/museum:",
    layout="wide",
)

navegacion = st.navigation(
    [
        st.Page("inicio.py", title="Colección", icon=":material/inventory_2:", default=True),
        st.Page("revision.py", title="Revisión", icon=":material/fact_check:", url_path="revision"),
        st.Page("acerca.py", title="Método y fuentes", icon=":material/info:", url_path="metodo"),
    ]
)
navegacion.run()
