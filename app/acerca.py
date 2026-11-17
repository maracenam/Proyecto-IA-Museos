"""Página pública: método, trazabilidad y fuentes."""

import pandas as pd
import streamlit as st

from comun import leer, pie

METODOS = {
    "regla_id": "Vocabulario (ID)",
    "sinonimo": "Vocabulario (sinónimo)",
    "llm": "IA local",
}

st.title("Método y fuentes")

st.markdown(
    """
**De dónde vienen los datos.** Las fichas públicas de la clasificación *Antropología, Arqueología
y Etnografía* del Museo Regional de Magallanes en [SURDOC](https://www.surdoc.cl). Se extraen cada
pocos días respetando el sitio (una solicitud cada 2 segundos y su `robots.txt`). El valor
original de cada ficha se guarda siempre sin cambios.

**Cómo se normaliza.** Tres campos se llevan a categorías comparables: tipo de objeto, material
(con su técnica) y estado de conservación.

1. **Vocabulario primero.** Si la ficha enlaza un término del AAT en español o del Tesauro
   Regional Patrimonial, se usa su categoría. Si no, se busca un sinónimo.
2. **IA local solo para lo que queda.** Un modelo de lenguaje abierto, que corre en un computador
   propio (ningún dato sale a servicios externos), propone una categoría con su confianza y una
   justificación. Solo puede elegir entre las categorías del vocabulario.
3. **Revisión humana.** Lo dudoso (confianza baja, "otro" o contradicción con la descripción) va a
   una cola de revisión. Las correcciones de una persona prevalecen sobre cualquier versión futura
   del modelo.

Cada valor guarda el original, el método, el modelo, la versión del prompt y la confianza.

**Lo que no se normaliza.** Datación y atribución cultural requieren criterio experto; se muestran
tal como vienen de SURDOC.

**Protección del patrimonio.** No se publican coordenadas ni nombres de sitios arqueológicos, y las
fotografías no se copian: se muestran desde SURDOC con el crédito del fotógrafo.
"""
)

valores = leer("valor_vigente")
if valores:
    df = pd.DataFrame(valores)
    resumen = (
        df.assign(Método=df["metodo"].map(METODOS))
        .groupby("Método").size().rename("Valores").reset_index()
    )  # fmt: skip
    st.subheader("Cómo se resolvió cada valor")
    st.dataframe(resumen, hide_index=True)
    st.caption(
        "La precisión por método se mide revisando a mano una muestra aleatoria de 50 valores por "
        "campo y se publica aquí cuando esa revisión esté completa."
    )

parametros = {p["clave"]: p["valor"] for p in leer("parametros")}
st.caption(f"Umbral de confianza para revisión: {parametros.get('umbral_confianza', '0.8')}")
pie()
