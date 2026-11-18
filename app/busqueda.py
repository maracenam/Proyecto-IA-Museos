"""Codificación de consultas para la búsqueda semántica.

Debe usar el mismo modelo que generó los embeddings de las fichas (pipeline/embed): por eso
el nombre del modelo viaja con cada búsqueda y la base solo compara vectores del mismo modelo.
El modelo se carga recién al primer uso y queda en caché para todas las sesiones."""

import streamlit as st

MODELO_POR_DEFECTO = "intfloat/multilingual-e5-small"


def prefijo_consulta(modelo: str) -> str:
    return "query: " if "e5" in modelo.lower() else ""


@st.cache_resource(show_spinner="Cargando el modelo de búsqueda (solo la primera vez)…")
def _modelo(nombre: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(nombre, device="cpu")


def vector_consulta(texto: str, modelo: str) -> str:
    vector = _modelo(modelo).encode(prefijo_consulta(modelo) + texto, normalize_embeddings=True)
    return "[" + ",".join(f"{x:.6f}" for x in vector.tolist()) + "]"
