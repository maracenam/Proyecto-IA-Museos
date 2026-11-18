"""Página pública: exploración de la colección (solo lectura)."""

import plotly.express as px
import streamlit as st

from comun import COLORES_ESTADO, leer, leyenda_validacion, pie
from logica import (
    NOMBRES_METODO,
    ORDEN_ESTADOS,
    SIN_DATO,
    coma,
    conteo_por_estado,
    filtrar,
    indicadores,
    orden_categorias,
    tabla_fichas,
    valores_de_ficha,
)

fichas = leer("fichas_publicas")
valores = leer("valor_vigente")
df = tabla_fichas(fichas, valores)

st.title("Colección arqueológica del Museo Regional de Magallanes")
st.markdown(
    "Fichas públicas de SURDOC con el **tipo de objeto, material y estado de conservación** "
    "llevados a categorías comparables. Cada valor indica si lo propuso el sistema o si lo "
    "validó una persona."
)

if df.empty:
    st.info(
        "Todavía no hay fichas cargadas. Aparecerán aquí después de la primera extracción "
        "(`python -m pipeline.run --museo 16`)."
    )
    st.stop()

ind = indicadores(fichas, valores)
por_vocabulario = 100 * ind["resueltos_por_reglas"] / max(ind["valores"], 1)
st.markdown(
    f"**{ind['fichas']}** fichas · **{ind['valores']}** valores normalizados · "
    f"**{por_vocabulario:.0f} %** resueltos por vocabulario, sin IA · "
    f"**{ind['en_revision']}** en revisión · **{ind['revisados']}** validados por una persona"
)

# Filtros en el cuerpo de la página: en celular el panel lateral viene cerrado y se pierden.
with st.container(border=True):
    texto = st.text_input(
        "Buscar en las fichas",
        placeholder="Boleadora, obsidiana, 16-9…",
        key="f_texto",
    )
    c1, c2, c3, c4, c5 = st.columns(5)

    def filtro(columna, etiqueta, opciones, clave):
        return columna.multiselect(etiqueta, sorted(opciones), placeholder="Todos", key=clave)

    tipos = filtro(c1, "Tipo de objeto", df["tipo"].unique(), "f_tipo")
    materiales = filtro(c2, "Material", df["material"].unique(), "f_material")
    conservacion = filtro(c3, "Conservación", df["conservacion"].unique(), "f_conservacion")
    colecciones = filtro(c4, "Colección", df["coleccion"].dropna().unique(), "f_col")
    validacion = c5.multiselect(
        "Validación", ORDEN_ESTADOS, placeholder="Todas", key="f_validacion"
    )

vista = filtrar(df, texto, tipos, materiales, conservacion, colecciones, validacion)

if vista.empty:
    st.warning("Ninguna ficha coincide con estos filtros. Quita alguno para ver resultados.")
    pie()
    st.stop()

st.caption(f"{len(vista)} de {len(df)} fichas")
leyenda_validacion([*ORDEN_ESTADOS, SIN_DATO])


def grafico(columna: str, titulo: str):
    datos = conteo_por_estado(vista, columna)
    figura = px.bar(
        datos, x="Fichas", y=columna, color="Validación", orientation="h",
        color_discrete_map=COLORES_ESTADO,
        category_orders={
            "Validación": [*ORDEN_ESTADOS, SIN_DATO],
            columna: orden_categorias(datos, columna),
        },
        title=titulo, labels={columna: ""},
    )  # fmt: skip
    figura.update_layout(
        height=max(200, 30 * datos[columna].nunique() + 70),
        margin={"l": 0, "r": 8, "t": 36, "b": 0},
        showlegend=False,
        xaxis_title=None,
        font={"color": "#3d4b54", "size": 13},
        title={"font": {"size": 15, "color": "#17232b"}},
        bargap=0.25,
    )
    figura.update_xaxes(gridcolor="#e3e9ec", zeroline=False)
    figura.update_traces(hovertemplate="%{y}: %{x} fichas<extra>%{fullData.name}</extra>")
    st.plotly_chart(figura, use_container_width=True, config={"displayModeBar": False})


g1, g2, g3 = st.columns([1.2, 1.2, 1], gap="large")
with g1:
    grafico("material", "Material")
with g2:
    grafico("tipo", "Tipo de objeto")
with g3:
    grafico("conservacion", "Estado de conservación")

st.subheader("Fichas")
st.caption("Selecciona una fila para ver su detalle, de dónde sale cada valor y la fotografía.")
seleccion = st.dataframe(
    vista[["surdoc_id", "objeto", "tipo", "tipo_estado", "material", "material_estado",
           "tecnica_material", "conservacion", "coleccion", "url_ficha"]],
    column_config={
        "surdoc_id": "Registro",
        "objeto": "Objeto en SURDOC",
        "tipo": "Tipo",
        "tipo_estado": "Validación (tipo)",
        "material": "Material",
        "material_estado": "Validación (material)",
        "tecnica_material": "Técnica / Material en SURDOC",
        "conservacion": "Conservación",
        "coleccion": "Colección",
        "url_ficha": st.column_config.LinkColumn("Ficha", display_text="Abrir en SURDOC"),
    },
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
    key="tabla_fichas",
)  # fmt: skip

filas = seleccion.selection.rows if seleccion else []
if filas and filas[0] < len(vista):
    ficha = vista.iloc[filas[0]]
    st.subheader(f"{ficha['objeto'] or 'Sin objeto'} · {ficha['surdoc_id']}")
    izquierda, derecha = st.columns([2, 1], gap="large")
    with izquierda:
        st.write(ficha["descripcion"] or "Sin descripción en SURDOC.")
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

    detalle = valores_de_ficha(valores, ficha["surdoc_id"])
    if not detalle.empty:
        st.markdown("**De dónde sale cada valor**")
        detalle = detalle.assign(
            Método=detalle["metodo"].map(NOMBRES_METODO),
            Confianza=detalle["confianza"].map(coma),
        )
        st.dataframe(
            detalle[["Campo", "entrada", "valor", "Validación", "Método", "Confianza",
                     "modelo", "version_prompt", "justificacion"]],
            column_config={
                "entrada": "Valor evaluado", "valor": "Valor vigente",
                "modelo": "Modelo", "version_prompt": "Prompt", "justificacion": "Justificación",
            },
            hide_index=True, use_container_width=True,
        )  # fmt: skip

st.caption(
    "Se normalizan el tipo de objeto, el material, la técnica y el estado de conservación. "
    "La cultura y el área geográfica se muestran tal como vienen de SURDOC."
)
pie()
