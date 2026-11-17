"""Página pública: exploración de la colección (solo lectura)."""

import plotly.express as px
import streamlit as st

from comun import leer, pie
from logica import (
    ESTADOS,
    NOMBRES_CAMPO,
    ORDEN_ESTADOS,
    SIN_DATO,
    conteo_por_estado,
    filtrar,
    indicadores,
    tabla_fichas,
    valores_de_ficha,
)

COLORES = {
    ESTADOS["revisado"]: "#5d6f2c",
    ESTADOS["propuesto"]: "#1f5f7a",
    ESTADOS["en_revision"]: "#c27a1a",
    SIN_DATO: "#9aa5ad",
}

fichas = leer("fichas_publicas")
valores = leer("valor_vigente")
df = tabla_fichas(fichas, valores)

st.title("Colección arqueológica del Museo Regional de Magallanes")
st.markdown(
    "Fichas públicas de SURDOC con el **tipo de objeto, material y estado de conservación "
    "normalizados** en categorías comparables. Cada valor indica si lo **propuso el sistema** "
    "(reglas o IA local) o si lo **revisó una persona**."
)

if df.empty:
    st.info(
        "Todavía no hay fichas cargadas. "
        "Ejecuta la extracción (`python -m pipeline.run --museo 16`)."
    )
    st.stop()

ind = indicadores(fichas, valores)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fichas", ind["fichas"])
c2.metric("Valores normalizados", ind["valores"], help="Tipo, material, técnica y conservación")
c3.metric(
    "Resueltos por vocabulario",
    f"{100 * ind['resueltos_por_reglas'] / max(ind['valores'], 1):.0f} %",
    help="Por ID del AAT o del Tesauro Regional, o por sinónimo, sin IA",
)
c4.metric("En revisión", ind["en_revision"], help="Confianza baja o conflicto con la descripción")

with st.sidebar:
    st.header("Filtros")
    texto = st.text_input("Buscar", placeholder="Boleadora, obsidiana, 16-9…", key="f_texto")

    def filtro(etiqueta, opciones, clave):
        return st.multiselect(etiqueta, sorted(opciones), placeholder="Todos", key=clave)

    tipos = filtro("Tipo de objeto", df["tipo"].unique(), "f_tipo")
    materiales = filtro("Material", df["material"].unique(), "f_material")
    conservacion = filtro("Estado de conservación", df["conservacion"].unique(), "f_conservacion")
    colecciones = filtro("Colección", df["coleccion"].dropna().unique(), "f_col")
    validacion = st.multiselect(
        "Validación", ORDEN_ESTADOS, placeholder="Todos", key="f_validacion"
    )

vista = filtrar(df, texto, tipos, materiales, conservacion, colecciones, validacion)
st.caption(f"{len(vista)} de {len(df)} fichas")


def grafico(columna: str, titulo: str):
    datos = conteo_por_estado(vista, columna)
    if datos.empty:
        return st.caption(f"{titulo}: sin datos con estos filtros.")
    figura = px.bar(
        datos, x="Fichas", y=columna, color="Validación", orientation="h",
        color_discrete_map=COLORES, category_orders={"Validación": [*ORDEN_ESTADOS, SIN_DATO]},
        title=titulo, labels={columna: ""},
    )  # fmt: skip
    figura.update_layout(
        height=max(240, 34 * datos[columna].nunique() + 110),
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        legend={"orientation": "h", "y": -0.18, "title": None},
        xaxis_title=None,
    )
    st.plotly_chart(figura, use_container_width=True)


g1, g2, g3 = st.columns([1.2, 1.2, 1])
with g1:
    grafico("material", "Material")
with g2:
    grafico("tipo", "Tipo de objeto")
with g3:
    grafico("conservacion", "Estado de conservación")

st.subheader("Fichas")
seleccion = st.dataframe(
    vista[["surdoc_id", "objeto", "tipo", "tipo_estado", "material", "material_estado",
           "tecnica_material", "conservacion", "coleccion", "url_ficha"]],
    column_config={
        "surdoc_id": "Registro",
        "objeto": "Objeto (original)",
        "tipo": "Tipo normalizado",
        "tipo_estado": "Validación del tipo",
        "material": "Material normalizado",
        "material_estado": "Validación del material",
        "tecnica_material": "Técnica / Material (original)",
        "conservacion": "Conservación",
        "coleccion": "Colección",
        "url_ficha": st.column_config.LinkColumn("SURDOC", display_text="Ver ficha"),
    },
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
    key="tabla_fichas",
)  # fmt: skip

filas = seleccion.selection.rows if seleccion else []
if filas:
    ficha = vista.iloc[filas[0]]
    st.subheader(f"{ficha['objeto'] or 'Sin objeto'} · {ficha['surdoc_id']}")
    izquierda, derecha = st.columns([2, 1])
    with izquierda:
        st.write(ficha["descripcion"] or "Sin descripción.")
        detalle = valores_de_ficha(valores, ficha["surdoc_id"])
        if not detalle.empty:
            st.dataframe(
                detalle[["Campo", "entrada", "valor", "Validación", "metodo", "confianza",
                         "modelo", "version_prompt", "justificacion"]],
                column_config={
                    "entrada": "Valor original evaluado", "valor": "Valor vigente",
                    "metodo": "Método",
                    "confianza": st.column_config.NumberColumn("Confianza", format="%.2f"),
                    "modelo": "Modelo",
                    "version_prompt": "Prompt",
                    "justificacion": "Justificación",
                },
                hide_index=True, use_container_width=True,
            )  # fmt: skip
        datos_ficha = {
            "Nº de inventario": ficha["numero_inventario"],
            "Clasificación": ficha["clasificacion"],
            "Dimensiones": ficha["dimensiones"],
            "Cultura": ficha["cultura_originaria"] or ficha["cultura_arqueologica"],
            "Área cultural": ficha["area_cultural"],
            "Área geográfica": ficha["area_geografica"],
        }
        st.markdown("  \n".join(f"**{k}:** {v}" for k, v in datos_ficha.items() if v))
        st.link_button("Ver ficha original en SURDOC", ficha["url_ficha"])
    with derecha:
        if ficha["url_imagen"]:
            st.image(
                ficha["url_imagen"],
                caption=f"Fotografía: {ficha['credito_imagen'] or 'sin crédito'} · SURDOC",
            )
else:
    st.caption(
        "Selecciona una fila para ver el detalle, la trazabilidad de cada valor y la fotografía."
    )

st.caption(
    "Los valores **propuestos** salen del vocabulario (AAT y Tesauro Regional) o de un modelo de "
    "lenguaje local; los **en revisión** tienen confianza baja o contradicen la descripción. "
    f"{', '.join(NOMBRES_CAMPO.values())} se normalizan; cultura y área geográfica se muestran "
    "tal como vienen de SURDOC."
)
pie()
