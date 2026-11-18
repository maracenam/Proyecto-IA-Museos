"""Normalización desde la línea de comandos (se ejecuta en el PC con Ollama).

python -m pipeline.normalize correr                      # reglas + LLM (LLM_MODELO)
python -m pipeline.normalize correr --sin-llm            # solo reglas
python -m pipeline.normalize muestra --campo material    # muestra para revisar en la app
python -m pipeline.normalize metricas                    # aciertos y umbral calibrado
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from pipeline.db import conectar
from pipeline.normalize.calidad import (
    calcular_metricas,
    crear_muestra,
    informe_markdown,
    leer_muestra_revisada,
    leer_revision,
)
from pipeline.normalize.llm import ModeloNoDisponible, Prompt, crear_normalizador
from pipeline.normalize.proceso import CAMPOS, ejecutar_normalizacion
from pipeline.normalize.vocabulario import Vocabulario, sincronizar_vocabulario


def _url_base() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("Falta DATABASE_URL (ver .env.example).")
    return url


def correr(args) -> int:
    campos = tuple(c.strip() for c in args.campos.split(",") if c.strip())
    if invalidos := set(campos) - set(CAMPOS):
        raise SystemExit(f"Campos no válidos: {sorted(invalidos)}. Opciones: {', '.join(CAMPOS)}")
    vocab = Vocabulario.cargar()
    prompt = Prompt.cargar(args.version)
    normalizador = None if args.sin_llm else crear_normalizador()
    with conectar(_url_base()) as con:
        logging.info("Vocabulario: %d términos sincronizados", sincronizar_vocabulario(con, vocab))
        try:
            r = ejecutar_normalizacion(con, vocab, prompt, normalizador, campos)
        except ModeloNoDisponible as error:
            logging.error(
                "%s. Lo procesado quedó guardado; vuelve a correr cuando esté disponible.", error
            )
            return 1
    d = r.detalle()
    logging.info(
        "Listo (prompt %s, modelo %s): %d pendientes, %d guardados %s, %d respuestas inválidas, "
        "%d sin resolver (requieren LLM), %d llamadas al LLM (mediana %s s), %.1f s en total",
        r.version_prompt, r.modelo or "ninguno", r.pendientes, r.guardados, r.por_metodo,
        r.respuestas_invalidas, r.sin_resolver, d["llamadas_llm"], d["segundos_llm_mediana"],
        r.segundos_totales,
    )  # fmt: skip
    return 0


def muestra(args) -> int:
    with conectar(_url_base()) as con:
        total, revisados = crear_muestra(con, args.campo, args.n, args.version, args.semilla)
    print(
        f"Muestra de {args.campo} ({args.version}): {total} valores, {revisados} revisados. "
        "Se revisa en la app: página Revisión → Muestra de calidad."
    )
    return 0


def metricas(args) -> int:
    if args.archivos:  # compatibilidad con revisiones hechas en CSV
        filas = leer_revision([Path(r) for r in args.archivos])
    else:
        with conectar(_url_base()) as con:
            filas = leer_muestra_revisada(con, args.campos.split(",") if args.campos else None)
    if not filas:
        raise SystemExit("Todavía no hay valores revisados en la muestra.")
    print(informe_markdown(calcular_metricas(filas, args.objetivo)))
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.normalize",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("correr", help="Normaliza los valores pendientes")
    p.add_argument("--campos", default=",".join(CAMPOS))
    p.add_argument("--version", default="v1", help="Versión de prompt (prompts/normalizar_<v>.md)")
    p.add_argument("--sin-llm", action="store_true", help="Solo reglas; lo demás queda pendiente")
    p.set_defaults(funcion=correr)

    p = sub.add_parser("muestra", help="Crea la muestra aleatoria para revisar en la app")
    p.add_argument("--campo", required=True, choices=CAMPOS)
    p.add_argument("--n", type=int, default=50)
    p.add_argument("--version", default="v1")
    p.add_argument("--semilla", type=int, default=2026)
    p.set_defaults(funcion=muestra)

    p = sub.add_parser("metricas", help="Aciertos por método y umbral calibrado")
    p.add_argument("archivos", nargs="*", help="CSV revisados (opcional; por defecto, la base)")
    p.add_argument("--campos", help="Limitar a estos campos, separados por coma")
    p.add_argument("--objetivo", type=float, default=0.95, help="Precisión mínima de lo aceptado")
    p.set_defaults(funcion=metricas)

    args = parser.parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":
    sys.exit(main())
