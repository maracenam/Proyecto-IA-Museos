"""Modelos de embeddings intercambiables.

El modelo se elige con EMBEDDING_MODELO (por defecto multilingual-e5-small, elegido en el
Sprint 4: 10/10 consultas de prueba con acierto en los 5 primeros). El mismo modelo debe
usarse en el pipeline (fichas) y en la app (consultas): por eso cada vector guarda su modelo."""

import os
from typing import Protocol

MODELO_POR_DEFECTO = "intfloat/multilingual-e5-small"


def modelo_configurado() -> str:
    return os.environ.get("EMBEDDING_MODELO", MODELO_POR_DEFECTO)


def prefijos(modelo: str) -> tuple[str, str]:
    """Los modelos E5 se entrenaron con prefijos distintos para consultas y documentos."""
    return ("query: ", "passage: ") if "e5" in modelo.lower() else ("", "")


class Codificador(Protocol):
    modelo: str

    def codificar(self, textos: list[str], son_consultas: bool = False) -> list[list[float]]: ...


class CodificadorSentenceTransformers:
    def __init__(self, modelo: str | None = None):
        from sentence_transformers import SentenceTransformer  # pesado: solo si se usa

        self.modelo = modelo or modelo_configurado()
        self._st = SentenceTransformer(self.modelo, device="cpu")
        self._prefijo_consulta, self._prefijo_documento = prefijos(self.modelo)

    def codificar(self, textos: list[str], son_consultas: bool = False) -> list[list[float]]:
        prefijo = self._prefijo_consulta if son_consultas else self._prefijo_documento
        vectores = self._st.encode(
            [prefijo + t for t in textos], normalize_embeddings=True, batch_size=32
        )
        return [v.tolist() for v in vectores]


def vector_sql(vector: list[float]) -> str:
    """Formato de texto que entiende pgvector: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
