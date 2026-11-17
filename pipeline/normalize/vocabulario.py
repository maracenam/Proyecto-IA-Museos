"""Vocabulario controlado del observatorio (vocab/*.csv) y su copia en la tabla `vocabulario`."""

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import psycopg

DIRECTORIO_VOCAB = Path(__file__).parents[2] / "vocab"


def sin_acentos(texto: str) -> str:
    """Minúsculas, sin acentos y con espacios simples: forma de comparar textos."""
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(plano.lower().split())


@dataclass(frozen=True)
class Categoria:
    campo: str
    nombre: str
    descripcion: str
    palabras_clave: tuple[str, ...]


@dataclass(frozen=True)
class TerminoVocab:
    campo: str
    fuente: str
    id_termino: str
    preferido: str
    sinonimos: tuple[str, ...]
    padre: str | None
    categoria: str


class Vocabulario:
    def __init__(self, categorias: list[Categoria], terminos: list[TerminoVocab]):
        self._categorias: dict[str, list[Categoria]] = {}
        for c in categorias:
            self._categorias.setdefault(c.campo, []).append(c)
        self.terminos = terminos
        self._por_id = {(t.campo, t.fuente, t.id_termino): t for t in terminos}
        self._por_texto: dict[tuple[str, str], TerminoVocab] = {}
        for t in terminos:
            nombres = self.nombres_categoria(t.campo)
            if t.categoria not in nombres:
                raise ValueError(
                    f"terminos.csv: {t.preferido!r} usa la categoría {t.categoria!r}, "
                    f"que no existe para {t.campo} en categorias.csv"
                )
            for texto in (t.preferido, *t.sinonimos):
                self._por_texto.setdefault((t.campo, sin_acentos(texto)), t)
        self._patrones = {
            (c.campo, c.nombre): [
                re.compile(rf"\b{re.escape(sin_acentos(p))}\b") for p in c.palabras_clave
            ]
            for c in categorias
        }

    @classmethod
    def cargar(cls, directorio: Path = DIRECTORIO_VOCAB) -> "Vocabulario":
        with open(directorio / "categorias.csv", encoding="utf-8") as archivo:
            categorias = [
                Categoria(
                    campo=f["campo"],
                    nombre=f["categoria"],
                    descripcion=f["descripcion"] or "",
                    palabras_clave=tuple(
                        p.strip() for p in f["palabras_clave"].split(";") if p.strip()
                    ),
                )
                for f in csv.DictReader(archivo)
            ]
        with open(directorio / "terminos.csv", encoding="utf-8") as archivo:
            terminos = [
                TerminoVocab(
                    campo=f["campo"],
                    fuente=f["fuente_termino"],
                    id_termino=f["id_termino"],
                    preferido=f["termino_preferido"],
                    sinonimos=tuple(s.strip() for s in f["sinonimos"].split(";") if s.strip()),
                    padre=f["termino_padre"] or None,
                    categoria=f["categoria"],
                )
                for f in csv.DictReader(archivo)
            ]
        return cls(categorias, terminos)

    def categorias(self, campo: str) -> list[Categoria]:
        if campo not in self._categorias:
            raise KeyError(f"No hay categorías para el campo {campo!r}")
        return self._categorias[campo]

    def nombres_categoria(self, campo: str) -> list[str]:
        return [c.nombre for c in self.categorias(campo)]

    def por_id(self, campo: str, fuente: str | None, id_termino: str | None) -> TerminoVocab | None:
        if not fuente or not id_termino:
            return None
        return self._por_id.get((campo, fuente, id_termino))

    def por_texto(self, campo: str, texto: str) -> TerminoVocab | None:
        return self._por_texto.get((campo, sin_acentos(texto)))

    def categorias_en_texto(self, campo: str, texto: str) -> set[str]:
        """Categorías cuyas palabras clave aparecen en el texto (palabra completa, sin acentos)."""
        plano = sin_acentos(texto or "")
        return {
            nombre
            for (c, nombre), patrones in self._patrones.items()
            if c == campo and any(p.search(plano) for p in patrones)
        }


def sincronizar_vocabulario(con: psycopg.Connection, vocab: Vocabulario) -> int:
    """Copia terminos.csv en la tabla `vocabulario` (upsert): la base queda autosuficiente."""
    with con.transaction(), con.cursor() as cur:
        cur.executemany(
            """insert into vocabulario
               (campo, fuente_termino, id_termino, termino_preferido, sinonimos,
                termino_padre, categoria)
               values (%s, %s, %s, %s, %s, %s, %s)
               on conflict (campo, fuente_termino, id_termino) do update set
                   termino_preferido = excluded.termino_preferido, sinonimos = excluded.sinonimos,
                   termino_padre = excluded.termino_padre, categoria = excluded.categoria""",
            [
                (
                    t.campo,
                    t.fuente,
                    t.id_termino,
                    t.preferido,
                    list(t.sinonimos),
                    t.padre,
                    t.categoria,
                )
                for t in vocab.terminos
            ],
        )
    return len(vocab.terminos)
