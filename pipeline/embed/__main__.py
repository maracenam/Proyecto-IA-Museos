"""Embeddings desde la línea de comandos (se ejecuta en el PC, como la normalización).

    python -m pipeline.embed generar                                   # solo los pendientes
    python -m pipeline.embed evaluar evaluacion/consultas_busqueda.csv  # aciertos en el top 5

Requiere el grupo de dependencias `embed`: `uv sync --group embed`."""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from pipeline.db import conectar
from pipeline.embed.codificador import CodificadorSentenceTransformers
from pipeline.embed.proceso import evaluar, generar_embeddings, informe_evaluacion


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.embed",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("generar", help="Genera los embeddings pendientes")
    p = sub.add_parser("evaluar", help="Mide la búsqueda con un conjunto de consultas")
    p.add_argument("archivo", nargs="?", default="evaluacion/consultas_busqueda.csv")
    p.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Falta DATABASE_URL (ver .env.example).")
    codificador = CodificadorSentenceTransformers()
    with conectar(url) as con:
        if args.comando == "generar":
            r = generar_embeddings(con, codificador)
            logging.info(
                "Listo (%s): %d fichas, %d pendientes, %d generados en %.1f s",
                r.modelo, r.fichas, r.pendientes, r.generados, r.segundos,
            )  # fmt: skip
        else:
            print(informe_evaluacion(evaluar(con, codificador, Path(args.archivo), args.k), args.k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
