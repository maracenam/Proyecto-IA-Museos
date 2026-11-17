"""Extracción incremental de un museo y clasificación (CU-01 y CU-02).

1. Recorre el listado de SURDOC.
2. Descarga cada ficha, la parsea y compara el hash de los campos parseados con el guardado:
   nueva o cambiada → se escribe en bronce y plata; igual → solo se marca como vista.
3. Una ficha que falla al descargar o parsear va a `cuarentena` y no detiene el lote.
4. Las fichas que ya no aparecen se marcan como dadas de baja, solo si el listado está
   completo (mismo total que informa SURDOC), para no dar de baja fichas por un listado parcial.
5. Todo queda registrado en `ejecuciones`."""

import logging
from dataclasses import asdict, dataclass, field

import psycopg

from pipeline import db
from pipeline.extract.cliente import ClienteSurdoc, ErrorDescarga, RutaProhibida
from pipeline.extract.listado import listar_ids
from pipeline.parse.ficha import ErrorParseo, parsear_ficha

log = logging.getLogger(__name__)


@dataclass
class Resumen:
    total_informado: int | None = None
    listados: int = 0
    nuevas_o_cambiadas: int = 0
    sin_cambios: int = 0
    en_cuarentena: list[str] = field(default_factory=list)
    dadas_de_baja: list[str] = field(default_factory=list)
    bajas_omitidas: str | None = None
    solicitudes: int = 0

    @property
    def procesadas(self) -> int:
        return self.nuevas_o_cambiadas + self.sin_cambios


def ejecutar_extraccion(
    con: psycopg.Connection,
    cliente: ClienteSurdoc,
    institucion: int,
    clasificacion: int,
    limite: int | None = None,
) -> Resumen:
    museo_id = db.obtener_museo_id(con, institucion)
    parametros = {"institucion": institucion, "clasificacion": clasificacion, "limite": limite}
    ejecucion_id = db.iniciar_ejecucion(con, "extraccion", parametros)
    resumen = Resumen()
    errores = 0
    try:
        listado = listar_ids(cliente, institucion, clasificacion)
        resumen.total_informado = listado.total_informado
        resumen.listados = len(listado.ids)
        log.info(
            "Listado: %d fichas en %d páginas (SURDOC informa %s)",
            len(listado.ids), listado.paginas, listado.total_informado,
        )  # fmt: skip
        ids = listado.ids[:limite] if limite else listado.ids

        for posicion, surdoc_id in enumerate(ids, 1):
            ruta = f"/registro/{surdoc_id}"
            url = f"{cliente.base_url}{ruta}"
            html = None
            try:
                html = cliente.obtener(ruta)
                ficha = parsear_ficha(html, surdoc_id, cliente.base_url)
            except (ErrorDescarga, RutaProhibida, ErrorParseo) as error:
                tipo = "parseo" if isinstance(error, ErrorParseo) else "descarga"
                log.warning("%s → cuarentena (%s): %s", surdoc_id, tipo, error)
                db.enviar_a_cuarentena(con, surdoc_id, url, f"{tipo}: {error}", html)
                resumen.en_cuarentena.append(surdoc_id)
                continue
            if db.hash_guardado(con, surdoc_id) == ficha.hash_campos():
                db.marcar_vista(con, surdoc_id)
                resumen.sin_cambios += 1
            else:
                db.guardar_ficha(con, ficha, url, museo_id)
                resumen.nuevas_o_cambiadas += 1
            if posicion % 10 == 0:
                log.info("%d/%d fichas", posicion, len(ids))

        if limite:
            resumen.bajas_omitidas = "ejecución con límite"
        elif not listado.completo:
            resumen.bajas_omitidas = (
                f"listado incompleto: {len(listado.ids)} de {listado.total_informado}"
            )
        else:
            resumen.dadas_de_baja = db.marcar_bajas(con, museo_id, listado.ids)
        if resumen.bajas_omitidas:
            log.warning("No se marcan bajas: %s", resumen.bajas_omitidas)
    except Exception as error:
        errores = 1
        log.exception("La extracción se detuvo: %s", error)
        raise
    finally:
        resumen.solicitudes = cliente.solicitudes
        db.cerrar_ejecucion(
            con,
            ejecucion_id,
            procesados=resumen.procesadas,
            en_cuarentena=len(resumen.en_cuarentena),
            dados_de_baja=len(resumen.dadas_de_baja),
            errores=errores,
            detalle=asdict(resumen),
        )
    return resumen
