"""Punto de entrada de la extracción.

    python -m pipeline.run --todos                 # todos los museos de la tabla `museos`
    python -m pipeline.run --museo 16              # un museo
    python -m pipeline.run --museo 16 --limite 5   # prueba corta (no marca bajas)

Códigos de salida (GitHub Actions avisa por correo cuando no es 0):
    0  todo bien
    1  la extracción de algún museo se detuvo (ej. no se pudo leer el listado)
    2  demasiadas fichas en cuarentena: probablemente SURDOC cambió su HTML
Si existe GITHUB_STEP_SUMMARY, escribe ahí un resumen en Markdown de la corrida."""

import argparse
import logging
import os
import sys
from dataclasses import dataclass

from pipeline.config import cargar_config
from pipeline.db import conectar
from pipeline.extract.cliente import ClienteSurdoc
from pipeline.extract.extraccion import Resumen, ejecutar_extraccion

CLASIFICACION_ARQUEOLOGIA = 548
UMBRAL_CUARENTENA = 0.2  # más del 20 % de las fichas en cuarentena = alarma

log = logging.getLogger(__name__)


@dataclass
class ResultadoMuseo:
    codigo: int
    nombre: str
    resumen: Resumen | None = None
    error: str | None = None

    @property
    def proporcion_cuarentena(self) -> float:
        if not self.resumen:
            return 0.0
        intentadas = self.resumen.procesadas + len(self.resumen.en_cuarentena)
        return len(self.resumen.en_cuarentena) / intentadas if intentadas else 0.0


def codigo_salida(resultados: list[ResultadoMuseo], umbral: float = UMBRAL_CUARENTENA) -> int:
    if any(r.error for r in resultados):
        return 1
    if any(r.proporcion_cuarentena > umbral for r in resultados):
        return 2
    return 0


def resumen_markdown(resultados: list[ResultadoMuseo], umbral: float = UMBRAL_CUARENTENA) -> str:
    lineas = [
        "## Extracción SURDOC",
        "",
        "| Museo | Listadas (SURDOC informa) | Nuevas o cambiadas | Sin cambios | Cuarentena "
        "| Dadas de baja | Estado |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        if r.error:
            lineas.append(f"| {r.nombre} ({r.codigo}) | — | — | — | — | — | ❌ {r.error} |")
            continue
        s = r.resumen
        estado = "⚠️ demasiada cuarentena" if r.proporcion_cuarentena > umbral else "✅"
        if s.bajas_omitidas and estado == "✅":
            estado = f"✅ (bajas omitidas: {s.bajas_omitidas})"
        lineas.append(
            f"| {r.nombre} ({r.codigo}) | {s.listados} ({s.total_informado}) | "
            f"{s.nuevas_o_cambiadas} | {s.sin_cambios} | {len(s.en_cuarentena)} | "
            f"{len(s.dadas_de_baja)} | {estado} |"
        )
    return "\n".join(lineas) + "\n"


def museos_a_extraer(con, codigo: int | None) -> list[tuple[int, str]]:
    if codigo is not None:
        fila = con.execute(
            "select codigo_institucion, nombre from museos where codigo_institucion = %s", (codigo,)
        ).fetchone()
        return [fila] if fila else [(codigo, f"Institución {codigo}")]
    return con.execute(
        "select codigo_institucion, nombre from museos order by codigo_institucion"
    ).fetchall()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extrae fichas de SURDOC a las capas bronce y plata."
    )
    destino = parser.add_mutually_exclusive_group(required=True)
    destino.add_argument("--museo", type=int, help="Código de institución (16 = Magallanes)")
    destino.add_argument("--todos", action="store_true", help="Todos los museos de la tabla museos")
    parser.add_argument("--clasificacion", type=int, default=CLASIFICACION_ARQUEOLOGIA)
    parser.add_argument(
        "--limite", type=int, help="Procesa solo las primeras N fichas (no marca bajas)"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # una línea por petición es ruido
    config = cargar_config()
    resultados: list[ResultadoMuseo] = []
    with (
        conectar(config.database_url) as con,
        ClienteSurdoc(
            config.surdoc_base_url, config.surdoc_user_agent, config.surdoc_pausa_segundos
        ) as cliente,
    ):
        for codigo, nombre in museos_a_extraer(con, None if args.todos else args.museo):
            resultado = ResultadoMuseo(codigo, nombre)
            try:
                resultado.resumen = ejecutar_extraccion(
                    con, cliente, codigo, args.clasificacion, args.limite
                )
            except Exception as error:  # un museo que falla no detiene a los demás
                resultado.error = f"{type(error).__name__}: {error}"[:200]
            resultados.append(resultado)

    for r in resultados:
        if r.resumen:
            s = r.resumen
            log.info(
                "%s: %d listadas (SURDOC informa %s), %d nuevas o cambiadas, %d sin cambios, "
                "%d en cuarentena %s, %d dadas de baja %s, %d solicitudes",
                r.nombre, s.listados, s.total_informado, s.nuevas_o_cambiadas, s.sin_cambios,
                len(s.en_cuarentena), s.en_cuarentena or "", len(s.dadas_de_baja),
                s.dadas_de_baja or "", s.solicitudes,
            )  # fmt: skip
        else:
            log.error("%s: la extracción se detuvo: %s", r.nombre, r.error)

    if ruta := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(ruta, "a", encoding="utf-8") as archivo:
            archivo.write(resumen_markdown(resultados))
    salida = codigo_salida(resultados)
    if salida == 2:
        log.error(
            "Más del %d %% de las fichas quedó en cuarentena: revisar si SURDOC cambió su HTML.",
            int(UMBRAL_CUARENTENA * 100),
        )
    return salida


if __name__ == "__main__":
    sys.exit(main())
