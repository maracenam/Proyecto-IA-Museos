"""Generación incremental de embeddings y evaluación de la búsqueda.

El texto de cada ficha usa solo campos públicos (vistas `fichas_publicas` y `valor_vigente`):
la tabla `embeddings` es de lectura pública y nunca debe contener datos sensibles
como el nombre de un sitio."""

import csv
import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import psycopg

from pipeline import db
from pipeline.embed.codificador import Codificador, vector_sql

log = logging.getLogger(__name__)


def textos_fichas(con: psycopg.Connection) -> dict[str, str]:
    filas = con.execute(
        """select f.surdoc_id, f.objeto, f.tecnica_material, f.coleccion, f.descripcion,
                  f.cultura_originaria, f.cultura_arqueologica, f.area_cultural,
                  (select string_agg(distinct v.valor, ', ')
                   from valor_vigente v
                   where v.surdoc_id = f.surdoc_id and v.campo in ('objeto', 'material', 'tecnica')
                     and v.valor <> 'otro') as categorias
           from fichas_publicas f order by f.surdoc_id"""
    ).fetchall()
    textos = {}
    for sid, objeto, tm, coleccion, desc, cult_o, cult_a, area, categorias in filas:
        partes = [
            f"Objeto: {objeto or 'sin dato'}.",
            f"Categorías: {categorias}." if categorias else "",
            f"Técnica y material: {tm}." if tm else "",
            f"Cultura: {cult_o or cult_a}." if (cult_o or cult_a) else "",
            f"Área cultural: {area}." if area else "",
            f"Colección: {coleccion}." if coleccion else "",
            f"Descripción: {desc}" if desc else "",
        ]
        textos[sid] = " ".join(p for p in partes if p)
    return textos


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass
class ResumenEmbeddings:
    modelo: str
    fichas: int = 0
    pendientes: int = 0
    generados: int = 0
    segundos: float = 0.0


def generar_embeddings(
    con: psycopg.Connection, codificador: Codificador, tamano_lote: int = 32
) -> ResumenEmbeddings:
    resumen = ResumenEmbeddings(modelo=codificador.modelo)
    ejecucion_id = db.iniciar_ejecucion(con, "embeddings", {"modelo": codificador.modelo})
    inicio = time.perf_counter()
    error = 0
    try:
        textos = textos_fichas(con)
        hechos = dict(
            con.execute(
                "select surdoc_id, hash_texto from embeddings where modelo = %s",
                (codificador.modelo,),
            ).fetchall()
        )
        pendientes = [(s, t) for s, t in textos.items() if hechos.get(s) != _hash(t)]
        resumen.fichas, resumen.pendientes = len(textos), len(pendientes)
        for i in range(0, len(pendientes), tamano_lote):
            lote = pendientes[i : i + tamano_lote]
            vectores = codificador.codificar([t for _, t in lote])
            with con.transaction(), con.cursor() as cur:
                cur.executemany(
                    """insert into embeddings (surdoc_id, modelo, vector, texto, hash_texto)
                       values (%s, %s, %s::extensions.vector, %s, %s)
                       on conflict (surdoc_id, modelo) do update set
                           vector = excluded.vector, texto = excluded.texto,
                           hash_texto = excluded.hash_texto, fecha = now()""",
                    [
                        (s, codificador.modelo, vector_sql(v), t, _hash(t))
                        for (s, t), v in zip(lote, vectores, strict=True)
                    ],
                )
            resumen.generados += len(lote)
    except Exception:
        error = 1
        raise
    finally:
        resumen.segundos = round(time.perf_counter() - inicio, 2)
        db.cerrar_ejecucion(
            con, ejecucion_id, procesados=resumen.generados, en_cuarentena=0,
            dados_de_baja=0, errores=error, detalle=asdict(resumen),
        )  # fmt: skip
    return resumen


def buscar(
    con: psycopg.Connection, codificador: Codificador, consulta: str, limite: int = 5
) -> list[tuple[str, float]]:
    """Misma función que usa la app (buscar_fichas), ejecutada como usuario anónimo."""
    vector = codificador.codificar([consulta], son_consultas=True)[0]
    with con.transaction():
        con.execute("set local role anon")
        filas = con.execute(
            "select surdoc_id, similitud from buscar_fichas(%s::extensions.vector, %s, %s)",
            (vector_sql(vector), codificador.modelo, limite),
        ).fetchall()
        con.execute("reset role")
    return [(s, float(sim)) for s, sim in filas]


@dataclass
class ResultadoConsulta:
    consulta: str
    pertinentes: set[str]
    top: list[str] = field(default_factory=list)

    @property
    def aciertos(self) -> int:
        return len(set(self.top) & self.pertinentes)


def evaluar(
    con: psycopg.Connection, codificador: Codificador, ruta: Path, k: int = 5
) -> list[ResultadoConsulta]:
    with open(ruta, encoding="utf-8") as archivo:
        consultas = list(csv.DictReader(archivo))
    resultados = []
    for c in consultas:
        r = ResultadoConsulta(c["consulta"], set(c["pertinentes"].split()))
        r.top = [s for s, _ in buscar(con, codificador, c["consulta"], k)]
        resultados.append(r)
    return resultados


def informe_evaluacion(resultados: list[ResultadoConsulta], k: int = 5) -> str:
    lineas = [
        f"| Consulta | Pertinentes en los {k} primeros | Primeros resultados |",
        "|---|---|---|",
    ]
    for r in resultados:
        lineas.append(
            f"| {r.consulta} | {r.aciertos}/{min(k, len(r.pertinentes))} | {' '.join(r.top)} |"
        )
    con_acierto = sum(r.aciertos > 0 for r in resultados)
    precision = sum(r.aciertos / k for r in resultados) / max(len(resultados), 1)
    lineas += [
        "",
        f"**Consultas con al menos un resultado pertinente en los {k} primeros:** "
        f"{con_acierto}/{len(resultados)} · **Precisión@{k} media:** {precision:.2f}",
    ]
    return "\n".join(lineas)
