"""Página pública: guía de uso. Muestra docs/MANUAL.md (una sola fuente para la app y el repo)."""

import re
from pathlib import Path

import streamlit as st

from comun import pie

DOCS = Path(__file__).parents[1] / "docs"
IMAGEN = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<ruta>[^)]+)\)\s*$")

# Ancho de lectura cómodo (~75 caracteres por línea) solo en esta página.
st.html("<style>.stMainBlockContainer{max-width:860px}</style>")

texto = (DOCS / "MANUAL.md").read_text(encoding="utf-8")
titulo, _, cuerpo = texto.partition("\n")
st.title(titulo.lstrip("# ").strip())

bloque: list[str] = []


def volcar() -> None:
    if bloque:
        st.markdown("\n".join(bloque))
        bloque.clear()


for linea in cuerpo.splitlines():
    imagen = IMAGEN.match(linea)
    if imagen:
        volcar()
        ruta = DOCS / imagen["ruta"]
        if ruta.exists():
            # Con marco, para que la captura no se confunda con controles reales.
            with st.container(border=True):
                st.image(str(ruta), caption=imagen["alt"])
        continue
    bloque.append(linea)
volcar()

pie(enlace_guia=False)
