"""Escritura en las capas bronce y plata, y en la tabla de auditoría `ejecuciones`.

Cada operación corre en `con.transaction()`: con una conexión en autocommit es una
transacción propia; dentro de otra transacción (pruebas) es un savepoint. Así, si
una ficha falla a mitad de camino, no deja filas a medias."""

import subprocess

import psycopg
from psycopg.types.json import Jsonb

from pipeline.parse.modelos import Ficha

COLUMNAS_REGISTRO = (
    "titulo", "numero_inventario", "clasificacion", "coleccion", "objeto", "descripcion",
    "dimensiones", "tecnica_material", "procedencia", "cultura_originaria",
    "cultura_arqueologica", "area_cultural", "area_geografica", "fecha_creacion", "creador",
    "forma_ingreso", "estado_conservacion",
)  # fmt: skip


def conectar(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=True)


def version_codigo() -> str:
    try:
        salida = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return salida.stdout.strip() or "desconocida"
    except (OSError, subprocess.SubprocessError):
        return "desconocida"


def obtener_museo_id(con: psycopg.Connection, codigo_institucion: int) -> int:
    fila = con.execute(
        "select id from museos where codigo_institucion = %s", (codigo_institucion,)
    ).fetchone()
    if fila is None:
        raise LookupError(f"La institución {codigo_institucion} no está en la tabla museos.")
    return fila[0]


def hash_guardado(con: psycopg.Connection, surdoc_id: str) -> str | None:
    fila = con.execute(
        "select hash_campos from registros_raw where surdoc_id = %s", (surdoc_id,)
    ).fetchone()
    return fila[0] if fila else None


def fila_registro(ficha: Ficha) -> dict:
    """Columnas publicables de la capa plata. Excluye a propósito nombre_sitio."""
    fila = {c: getattr(ficha, c) for c in COLUMNAS_REGISTRO}
    if ficha.imagenes:
        fila["url_imagen"] = ficha.imagenes[0].url
        fila["credito_imagen"] = ficha.imagenes[0].credito
    else:
        fila["url_imagen"] = fila["credito_imagen"] = None
    return fila


def guardar_ficha(con: psycopg.Connection, ficha: Ficha, url: str, museo_id: int) -> None:
    """Inserta o actualiza la ficha en bronce y plata y reemplaza sus términos."""
    fila = fila_registro(ficha)
    columnas = list(fila)
    with con.transaction():
        con.execute(
            """insert into registros_raw (surdoc_id, url, campos, hash_campos)
               values (%s, %s, %s, %s)
               on conflict (surdoc_id) do update set
                   url = excluded.url, campos = excluded.campos,
                   hash_campos = excluded.hash_campos,
                   fecha_extraccion = now(), fecha_ultima_vista = now()""",
            (ficha.surdoc_id, url, Jsonb(ficha.campos()), ficha.hash_campos()),
        )
        con.execute(
            f"""insert into registros (surdoc_id, museo_id, {", ".join(columnas)})
                values (%s, %s, {", ".join(["%s"] * len(columnas))})
                on conflict (surdoc_id) do update set
                    museo_id = excluded.museo_id,
                    {", ".join(f"{c} = excluded.{c}" for c in columnas)},
                    dado_de_baja = false, fecha_baja = null, actualizado_en = now()""",
            (ficha.surdoc_id, museo_id, *fila.values()),
        )
        con.execute("delete from registro_terminos where surdoc_id = %s", (ficha.surdoc_id,))
        with con.cursor() as cur:
            cur.executemany(
                """insert into registro_terminos
                   (surdoc_id, campo, orden, grupo, texto_original, fuente_termino, id_termino)
                   values (%s, %s, %s, %s, %s, %s, %s)""",
                [
                    (ficha.surdoc_id, t.campo, t.orden, t.grupo, t.texto, t.fuente, t.id_termino)
                    for t in ficha.terminos
                ],
            )


def marcar_vista(con: psycopg.Connection, surdoc_id: str) -> None:
    """La ficha sigue igual: solo se registra que se vio, y se reactiva si estaba de baja."""
    with con.transaction():
        con.execute(
            "update registros_raw set fecha_ultima_vista = now() where surdoc_id = %s",
            (surdoc_id,),
        )
        con.execute(
            """update registros set dado_de_baja = false, fecha_baja = null, actualizado_en = now()
               where surdoc_id = %s and dado_de_baja""",
            (surdoc_id,),
        )


def enviar_a_cuarentena(
    con: psycopg.Connection, surdoc_id: str, url: str, error: str, html: str | None
) -> None:
    with con.transaction():
        con.execute(
            "insert into cuarentena (surdoc_id, url, error, html) values (%s, %s, %s, %s)",
            (surdoc_id, url, error[:4000], html),
        )


def marcar_bajas(con: psycopg.Connection, museo_id: int, ids_vistos: list[str]) -> list[str]:
    """Marca como dadas de baja (sin borrarlas) las fichas del museo que ya no están en SURDOC."""
    with con.transaction():
        filas = con.execute(
            """update registros set dado_de_baja = true, fecha_baja = now(), actualizado_en = now()
               where museo_id = %s and not dado_de_baja and not (surdoc_id = any(%s))
               returning surdoc_id""",
            (museo_id, ids_vistos),
        ).fetchall()
    return sorted(f[0] for f in filas)


def iniciar_ejecucion(con: psycopg.Connection, tipo: str, detalle: dict) -> int:
    with con.transaction():
        return con.execute(
            """insert into ejecuciones (tipo_proceso, detalle, version_codigo)
               values (%s, %s, %s) returning id""",
            (tipo, Jsonb(detalle), version_codigo()),
        ).fetchone()[0]


def cerrar_ejecucion(
    con: psycopg.Connection,
    ejecucion_id: int,
    procesados: int,
    en_cuarentena: int,
    dados_de_baja: int,
    errores: int,
    detalle: dict,
) -> None:
    with con.transaction():
        con.execute(
            """update ejecuciones set fin = now(), registros_procesados = %s, en_cuarentena = %s,
                   dados_de_baja = %s, errores = %s, detalle = coalesce(detalle, '{}') || %s
               where id = %s""",
            (procesados, en_cuarentena, dados_de_baja, errores, Jsonb(detalle), ejecucion_id),
        )
