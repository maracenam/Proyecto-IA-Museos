"""Punto de entrada del pipeline.

    python -m pipeline.run --museo 16
    python -m pipeline.run --museo 16 --clasificacion 548 --limite 5

Termina con código 1 si la extracción se detiene (por ejemplo, si no se puede leer
el listado); las fichas en cuarentena no cuentan como falla de la ejecución."""

import argparse
import logging
import sys

from pipeline.config import cargar_config
from pipeline.db import conectar
from pipeline.extract.cliente import ClienteSurdoc
from pipeline.extract.extraccion import ejecutar_extraccion

CLASIFICACION_ARQUEOLOGIA = 548


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extrae fichas de SURDOC a las capas bronce y plata."
    )
    parser.add_argument(
        "--museo", type=int, required=True, help="Código de institución (16 = Magallanes)"
    )
    parser.add_argument("--clasificacion", type=int, default=CLASIFICACION_ARQUEOLOGIA)
    parser.add_argument(
        "--limite", type=int, help="Procesa solo las primeras N fichas (no marca bajas)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # una línea por petición es ruido
    config = cargar_config()
    with (
        conectar(config.database_url) as con,
        ClienteSurdoc(
            config.surdoc_base_url, config.surdoc_user_agent, config.surdoc_pausa_segundos
        ) as cliente,
    ):
        try:
            resumen = ejecutar_extraccion(con, cliente, args.museo, args.clasificacion, args.limite)
        except Exception:
            return 1
    logging.info(
        "Listo: %d listadas (SURDOC informa %s), %d nuevas o cambiadas, %d sin cambios, "
        "%d en cuarentena %s, %d dadas de baja %s, %d solicitudes",
        resumen.listados, resumen.total_informado, resumen.nuevas_o_cambiadas,
        resumen.sin_cambios, len(resumen.en_cuarentena), resumen.en_cuarentena or "",
        len(resumen.dadas_de_baja), resumen.dadas_de_baja or "", resumen.solicitudes,
    )  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
