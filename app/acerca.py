"""Página pública: método, trazabilidad y fuentes."""

import pandas as pd
import streamlit as st

from comun import leer, pie
from logica import NOMBRES_METODO, coma, metricas_muestra

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
    orden = list(NOMBRES_METODO.values())  # el orden del proceso: vocabulario primero, IA al final
    resumen = (
        df.assign(Método=df["metodo"].map(NOMBRES_METODO))
        .groupby("Método").size().rename("Valores").reindex(orden).dropna().astype(int)
        .reset_index()
    )  # fmt: skip
    resumen["Proporción"] = resumen["Valores"] / resumen["Valores"].sum()
    st.subheader("Cómo se resolvió cada valor")
    st.dataframe(
        resumen,
        column_config={
            "Proporción": st.column_config.ProgressColumn(
                format="percent", min_value=0, max_value=1
            )
        },
        hide_index=True,
    )

st.subheader("Precisión medida por personas")
m = metricas_muestra(leer("muestra_calidad_detalle"))
if not m["revisados"]:
    st.markdown(
        "La precisión se mide revisando a mano una muestra aleatoria de valores. Se publicará "
        "aquí en cuanto empiece esa revisión."
    )
else:
    st.markdown(
        f"**{100 * m['precision']:.0f} %** de aciertos en **{m['revisados']}** valores "
        f"revisados de una muestra de {m['total']}."
    )
    st.dataframe(
        m["por_metodo"],
        column_config={
            "Precisión": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)
        },
        hide_index=True,
    )
    if m["umbral_recomendado"] is not None:
        st.caption(
            f"Con un umbral de confianza de {coma(m['umbral_recomendado'])}, lo que se acepta sin "
            f"revisión alcanza al menos {100 * m['objetivo']:.0f} % de precisión en la muestra."
        )
    if m["revisados"] < m["total"]:
        st.caption("Resultados parciales: la revisión de la muestra sigue en curso.")

parametros = {p["clave"]: p["valor"] for p in leer("parametros")}
umbral = float(parametros.get("umbral_confianza", "0.8"))
st.caption(f"Hoy, los valores con confianza menor a {coma(umbral, 1)} pasan a revisión humana.")
pie()
