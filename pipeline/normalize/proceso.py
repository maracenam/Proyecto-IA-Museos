"""Normalización de los valores pendientes (CU-03).

Para cada valor: reglas (ID → sinónimo) y, si no alcanzan, el LLM. Se guarda en
`normalizaciones` con método, confianza, modelo, versión de prompt, origen y entrada.
Es incremental: solo procesa valores sin normalización para esta versión de prompt o
cuya ficha cambió después de normalizarse. Nunca toca `revisiones`."""

import logging
import statistics
import time
from dataclasses import asdict, dataclass, field

import psycopg

from pipeline import db
from pipeline.normalize.llm import Normalizador, Prompt, RespuestaInvalida
from pipeline.normalize.reglas import Caso, Propuesta, aplicar_reglas
from pipeline.normalize.vocabulario import Vocabulario

log = logging.getLogger(__name__)

CAMPOS = ("objeto", "material", "tecnica", "estado_conservacion")
CAMPOS_DESDE_DESCRIPCION = ("objeto", "material")  # si la ficha no los declara
INTENTOS_LLM = 2  # el original y un reintento; luego, a revisión


@dataclass
class ResumenNormalizacion:
    version_prompt: str
    modelo: str | None
    pendientes: int = 0
    por_metodo: dict[str, int] = field(default_factory=dict)
    respuestas_invalidas: int = 0
    sin_resolver: int = 0  # requieren LLM pero se corrió con --sin-llm
    segundos_totales: float = 0.0
    segundos_llm: list[float] = field(default_factory=list)

    @property
    def guardados(self) -> int:
        return sum(self.por_metodo.values())

    def detalle(self) -> dict:
        datos = asdict(self)
        tiempos = datos.pop("segundos_llm")
        datos["llamadas_llm"] = len(tiempos)
        datos["segundos_llm_total"] = round(sum(tiempos), 2)
        datos["segundos_llm_mediana"] = round(statistics.median(tiempos), 2) if tiempos else None
        datos["segundos_totales"] = round(self.segundos_totales, 2)
        return datos


def construir_casos(con: psycopg.Connection, campos: tuple[str, ...] = CAMPOS) -> list[Caso]:
    fichas = con.execute(
        """select r.surdoc_id, r.objeto, r.tecnica_material, r.descripcion,
                  r.estado_conservacion, raw.hash_campos
           from registros r join registros_raw raw using (surdoc_id)
           where not r.dado_de_baja order by r.surdoc_id"""
    ).fetchall()
    terminos: dict[str, list[tuple]] = {}
    for fila in con.execute(
        """select surdoc_id, campo, orden, texto_original, fuente_termino, id_termino
           from registro_terminos order by surdoc_id, campo, orden"""
    ):
        terminos.setdefault(fila[0], []).append(fila[1:])

    casos = []
    for surdoc_id, objeto, tecnica_material, descripcion, estado, hash_ficha in fichas:
        contexto = {
            "hash_ficha": hash_ficha,
            "objeto": objeto,
            "tecnica_material": tecnica_material,
            "descripcion": descripcion,
            "materiales_declarados": tuple(
                (t[2], t[3], t[4]) for t in terminos.get(surdoc_id, []) if t[0] == "material"
            ),
        }
        for campo in campos:
            if campo == "estado_conservacion":
                if estado:
                    casos.append(Caso(surdoc_id, campo, 0, "campo", estado, contexto=contexto))
                continue
            propios = [t for t in terminos.get(surdoc_id, []) if t[0] == campo]
            for _, orden, texto, fuente, id_termino in propios:
                casos.append(
                    Caso(surdoc_id, campo, orden, "termino", texto, fuente, id_termino, contexto)
                )
            if not propios and campo in CAMPOS_DESDE_DESCRIPCION and descripcion:
                casos.append(
                    Caso(surdoc_id, campo, 0, "descripcion", descripcion, contexto=contexto)
                )
    return casos


def filtrar_pendientes(
    con: psycopg.Connection, casos: list[Caso], version_prompt: str
) -> list[Caso]:
    """Pendiente = sin normalización en esta versión, o hecha sobre otra versión de la ficha
    (el hash guardado no coincide con el actual: la ficha cambió en SURDOC)."""
    hechos = {
        (s, c, o)
        for s, c, o in con.execute(
            """select n.surdoc_id, n.campo, n.orden from normalizaciones n
               join registros_raw raw using (surdoc_id)
               where n.version_prompt = %s and n.hash_ficha = raw.hash_campos""",
            (version_prompt,),
        )
    }
    return [c for c in casos if c.clave not in hechos]


def consultar_llm(
    normalizador: Normalizador, prompt: Prompt, caso: Caso, vocab: Vocabulario
) -> tuple[Propuesta, list[float], bool]:
    """Devuelve la propuesta, el tiempo de cada intento y si la respuesta fue inválida."""
    categorias = vocab.categorias(caso.campo)
    sistema = prompt.sistema(caso.campo, [(c.nombre, c.descripcion) for c in categorias])
    mensaje = Prompt.mensaje(caso)
    tiempos, ultimo_error = [], ""
    for _ in range(INTENTOS_LLM):
        inicio = time.perf_counter()
        try:
            r = normalizador.proponer(sistema, mensaje, [c.nombre for c in categorias])
        except RespuestaInvalida as error:
            ultimo_error = str(error)
            continue
        finally:
            tiempos.append(time.perf_counter() - inicio)
        return (
            Propuesta(r.valor, "llm", r.confianza, r.justificacion, normalizador.modelo),
            tiempos,
            False,
        )
    justificacion = f"Respuesta inválida del modelo tras {INTENTOS_LLM} intentos: {ultimo_error}"
    return Propuesta("otro", "llm", 0.0, justificacion[:1000], normalizador.modelo), tiempos, True


def guardar_normalizacion(
    con: psycopg.Connection, caso: Caso, propuesta: Propuesta, version_prompt: str
) -> None:
    with con.transaction():
        con.execute(
            """insert into normalizaciones (surdoc_id, campo, orden, version_prompt,
                   valor_normalizado, metodo, confianza, modelo, justificacion, origen, entrada,
                   hash_ficha)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (surdoc_id, campo, orden, version_prompt) do update set
                   valor_normalizado = excluded.valor_normalizado, metodo = excluded.metodo,
                   confianza = excluded.confianza, modelo = excluded.modelo,
                   justificacion = excluded.justificacion, origen = excluded.origen,
                   entrada = excluded.entrada, hash_ficha = excluded.hash_ficha,
                   fecha = now()""",
            (
                caso.surdoc_id, caso.campo, caso.orden, version_prompt, propuesta.valor,
                propuesta.metodo, round(propuesta.confianza, 3), propuesta.modelo,
                propuesta.justificacion, caso.origen, caso.entrada[:2000],
                caso.contexto.get("hash_ficha"),
            ),
        )  # fmt: skip


def ejecutar_normalizacion(
    con: psycopg.Connection,
    vocab: Vocabulario,
    prompt: Prompt,
    normalizador: Normalizador | None,
    campos: tuple[str, ...] = CAMPOS,
) -> ResumenNormalizacion:
    """Normaliza los pendientes. Con normalizador=None solo aplica reglas (--sin-llm)."""
    modelo = normalizador.modelo if normalizador else None
    resumen = ResumenNormalizacion(version_prompt=prompt.version, modelo=modelo)
    ejecucion_id = db.iniciar_ejecucion(
        con, "normalizacion", {"version_prompt": prompt.version, "modelo": modelo, "campos": campos}
    )
    inicio = time.perf_counter()
    error = 0
    try:
        pendientes = filtrar_pendientes(con, construir_casos(con, campos), prompt.version)
        resumen.pendientes = len(pendientes)
        log.info("%d valores pendientes (prompt %s)", len(pendientes), prompt.version)
        for i, caso in enumerate(pendientes, 1):
            propuesta = aplicar_reglas(caso, vocab)
            if propuesta is None:
                if normalizador is None:
                    resumen.sin_resolver += 1
                    continue
                propuesta, tiempos, invalida = consultar_llm(normalizador, prompt, caso, vocab)
                resumen.segundos_llm.extend(tiempos)
                resumen.respuestas_invalidas += invalida
            guardar_normalizacion(con, caso, propuesta, prompt.version)
            resumen.por_metodo[propuesta.metodo] = resumen.por_metodo.get(propuesta.metodo, 0) + 1
            if i % 25 == 0:
                log.info("%d/%d valores", i, len(pendientes))
    except Exception:
        error = 1
        raise
    finally:
        resumen.segundos_totales = time.perf_counter() - inicio
        db.cerrar_ejecucion(
            con,
            ejecucion_id,
            procesados=resumen.guardados,
            en_cuarentena=0,
            dados_de_baja=0,
            errores=error + resumen.respuestas_invalidas,
            detalle=resumen.detalle(),
        )
    return resumen
