"""Medición de calidad (Sprint 2): muestra para revisión humana, aciertos por método
y calibración del umbral de confianza.

Flujo:
1. `muestra` exporta un CSV con una muestra aleatoria (semilla fija) de valores normalizados.
2. Una persona (idealmente la arqueóloga) completa la columna `valor_correcto`.
3. `metricas` calcula aciertos por método y propone el umbral: el menor valor de confianza
   con el que lo que se acepta sin revisión alcanza la precisión objetivo."""

import csv
import random
from dataclasses import dataclass
from pathlib import Path

import psycopg

from pipeline.normalize.vocabulario import sin_acentos

COLUMNAS_MUESTRA = (
    "surdoc_id", "campo", "orden", "origen", "objeto", "entrada", "valor_propuesto", "metodo",
    "confianza", "justificacion", "url_ficha", "valor_correcto", "comentario",
)  # fmt: skip
UMBRALES = tuple(round(0.5 + 0.05 * i, 2) for i in range(10))  # 0,50 … 0,95


def exportar_muestra(
    con: psycopg.Connection, campo: str, n: int, version_prompt: str, semilla: int, ruta: Path
) -> int:
    filas = con.execute(
        """select n.surdoc_id, n.campo, n.orden, n.origen, r.objeto, n.entrada, n.valor_normalizado,
                  n.metodo, n.confianza, n.justificacion
           from normalizaciones n join registros r using (surdoc_id)
           where n.campo = %s and n.version_prompt = %s and not r.dado_de_baja
           order by n.surdoc_id, n.orden""",
        (campo, version_prompt),
    ).fetchall()
    muestra = random.Random(semilla).sample(filas, min(n, len(filas)))
    muestra.sort(key=lambda f: (f[0], f[2]))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8-sig", newline="") as archivo:  # utf-8-sig: lo abre Excel
        escritor = csv.writer(archivo)
        escritor.writerow(COLUMNAS_MUESTRA)
        for f in muestra:
            entrada = (f[5] or "")[:400]
            escritor.writerow(
                [*f[:5], entrada, f[6], f[7], f"{f[8]:.2f}", f[9],
                 f"https://www.surdoc.cl/registro/{f[0]}", "", ""]
            )  # fmt: skip
    return len(muestra)


@dataclass(frozen=True)
class FilaRevisada:
    metodo: str
    confianza: float
    acierto: bool


def leer_revision(rutas: list[Path]) -> list[FilaRevisada]:
    """Lee CSV revisados. Las filas sin `valor_correcto` se ignoran (no revisadas)."""
    filas = []
    for ruta in rutas:
        with open(ruta, encoding="utf-8-sig", newline="") as archivo:
            for f in csv.DictReader(archivo):
                correcto = (f.get("valor_correcto") or "").strip()
                if not correcto:
                    continue
                filas.append(
                    FilaRevisada(
                        metodo=f["metodo"],
                        confianza=float(f["confianza"].replace(",", ".")),
                        acierto=sin_acentos(correcto) == sin_acentos(f["valor_propuesto"]),
                    )
                )
    return filas


def calcular_metricas(filas: list[FilaRevisada], objetivo: float = 0.95) -> dict:
    por_metodo = {}
    for metodo in sorted({f.metodo for f in filas}):
        grupo = [f for f in filas if f.metodo == metodo]
        aciertos = sum(f.acierto for f in grupo)
        por_metodo[metodo] = {
            "n": len(grupo),
            "aciertos": aciertos,
            "precision": aciertos / len(grupo),
        }
    calibracion = []
    for umbral in UMBRALES:
        aceptados = [f for f in filas if f.confianza >= umbral]
        precision = sum(f.acierto for f in aceptados) / len(aceptados) if aceptados else None
        calibracion.append(
            {
                "umbral": umbral,
                "aceptados": len(aceptados),
                "a_revision": len(filas) - len(aceptados),
                "precision_aceptados": precision,
            }
        )
    recomendado = next(
        (
            c["umbral"]
            for c in calibracion
            if c["aceptados"] and c["precision_aceptados"] >= objetivo
        ),
        None,
    )
    total = len(filas)
    return {
        "revisados": total,
        "aciertos": sum(f.acierto for f in filas),
        "precision": sum(f.acierto for f in filas) / total if total else None,
        "por_metodo": por_metodo,
        "calibracion": calibracion,
        "objetivo": objetivo,
        "umbral_recomendado": recomendado,
    }


def _pct(valor: float | None) -> str:
    return "—" if valor is None else f"{100 * valor:.0f} %"


def informe_markdown(metricas: dict) -> str:
    lineas = [
        f"**Revisados:** {metricas['revisados']} · **Aciertos:** {metricas['aciertos']} "
        f"({_pct(metricas['precision'])})",
        "",
        "| Método | Revisados | Aciertos | Precisión |",
        "|---|---|---|---|",
    ]
    for metodo, m in metricas["por_metodo"].items():
        lineas.append(f"| {metodo} | {m['n']} | {m['aciertos']} | {_pct(m['precision'])} |")
    lineas += [
        "",
        "| Umbral | Aceptados sin revisión | A revisión | Precisión de los aceptados |",
        "|---|---|---|---|",
    ]
    for c in metricas["calibracion"]:
        lineas.append(
            f"| {c['umbral']:.2f} | {c['aceptados']} | {c['a_revision']} | "
            f"{_pct(c['precision_aceptados'])} |"
        )
    recomendado = metricas["umbral_recomendado"]
    lineas += [
        "",
        f"**Umbral recomendado** (precisión ≥ {_pct(metricas['objetivo'])}): "
        + (f"{recomendado:.2f}" if recomendado is not None else "ninguno lo alcanza; revisar todo"),
    ]
    return "\n".join(lineas)


# --- Muestra en la base (se revisa desde la app, página Revisión → Muestra de calidad) ---

SQL_CREAR_MUESTRA = """
insert into muestra_calidad
    (surdoc_id, campo, orden, version_prompt, posicion, valor_propuesto, metodo, confianza)
select surdoc_id, campo, orden, version_prompt,
       row_number() over (order by orden_azar), valor_normalizado, metodo, confianza
from (
    select n.*, md5(n.surdoc_id || '|' || n.campo || '|' || n.orden || '|' || %(semilla)s)
                as orden_azar
    from normalizaciones n
    join registros r using (surdoc_id)
    where n.campo = %(campo)s and n.version_prompt = %(version)s and not r.dado_de_baja
    order by orden_azar
    limit %(n)s
) elegidos
on conflict do nothing
"""


def crear_muestra(
    con: psycopg.Connection, campo: str, n: int, version_prompt: str, semilla: int
) -> tuple[int, int]:
    """Crea la muestra de un campo si no existe (orden al azar pero reproducible con la semilla).
    No toca respuestas ya dadas. Devuelve (valores en la muestra, ya revisados)."""
    existentes = con.execute(
        "select count(*) from muestra_calidad where campo = %s and version_prompt = %s",
        (campo, version_prompt),
    ).fetchone()[0]
    if existentes == 0:
        with con.transaction():
            con.execute(
                SQL_CREAR_MUESTRA,
                {"campo": campo, "version": version_prompt, "n": n, "semilla": str(semilla)},
            )
    return con.execute(
        "select count(*), count(valor_correcto) from muestra_calidad "
        "where campo = %s and version_prompt = %s",
        (campo, version_prompt),
    ).fetchone()


def leer_muestra_revisada(
    con: psycopg.Connection, campos: list[str] | None = None
) -> list[FilaRevisada]:
    filas = con.execute(
        """select metodo, confianza, valor_propuesto, valor_correcto from muestra_calidad
           where valor_correcto is not null
             and (%(campos)s::text[] is null or campo = any(%(campos)s))""",
        {"campos": campos},
    ).fetchall()
    return [
        FilaRevisada(metodo, float(conf), sin_acentos(correcto) == sin_acentos(propuesto))
        for metodo, conf, propuesto, correcto in filas
    ]
