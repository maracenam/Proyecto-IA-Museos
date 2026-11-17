"""Pruebas de las migraciones contra un Postgres real (docker compose).
Se omiten si DATABASE_URL no está definida o la base no responde."""

import os
import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

MIGRACIONES = sorted((Path(__file__).parents[1] / "db" / "migrations").glob("*.sql"))
TABLAS = {
    "museos",
    "registros_raw",
    "cuarentena",
    "registros",
    "registro_terminos",
    "vocabulario",
    "normalizaciones",
    "revisores",
    "revisiones",
    "embeddings",
    "ejecuciones",
}


@pytest.fixture(scope="module")
def conexion():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL no definida")
    try:
        con = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError as error:
        pytest.skip(f"Base no disponible: {error}")
    yield con
    con.close()


@pytest.fixture
def transaccion(conexion):
    """Cada prueba corre en una transacción que se revierte."""
    with conexion.transaction(force_rollback=True):
        yield conexion


def test_migraciones_son_idempotentes(conexion):
    for _ in range(2):
        for archivo in MIGRACIONES:
            conexion.execute(archivo.read_text(encoding="utf-8"))
    filas = conexion.execute("select count(*) from museos where codigo_institucion = 16").fetchone()
    assert filas[0] == 1


def test_existen_todas_las_tablas_con_rls(conexion):
    filas = conexion.execute(
        "select relname, relrowsecurity from pg_class "
        "where relnamespace = 'public'::regnamespace and relkind = 'r'"
    ).fetchall()
    estado = dict(filas)
    assert TABLAS <= estado.keys()
    assert all(estado[t] for t in TABLAS)


def test_pgvector_instalado(conexion):
    assert conexion.execute("select 1 from pg_extension where extname = 'vector'").fetchone()


def _como(con, rol: str, uid: uuid.UUID | None = None):
    con.execute(f"set local role {rol}")
    if uid:
        con.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(uid),))


def _sembrar_registro(con, surdoc_id: str = "16-0"):
    con.execute(
        "insert into registros_raw (surdoc_id, url, campos, hash_campos) "
        "values (%s, 'u', '{}', 'h')",
        (surdoc_id,),
    )
    con.execute("insert into registros (surdoc_id, museo_id) values (%s, 1)", (surdoc_id,))


def test_anon_lee_plata_pero_no_bronce(transaccion):
    _sembrar_registro(transaccion)
    _como(transaccion, "anon")
    assert transaccion.execute("select count(*) from registros").fetchone()[0] >= 1
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        transaccion.execute("select * from registros_raw")


def test_anon_no_escribe(transaccion):
    _como(transaccion, "anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        transaccion.execute("insert into museos (nombre, codigo_institucion) values ('x', 999)")


def _insertar_revision(con, revisado_por: uuid.UUID):
    con.execute(
        "insert into revisiones (surdoc_id, campo, orden, valor_corregido, revisado_por) "
        "values ('16-0', 'material', 0, 'cerámica', %s)",
        (str(revisado_por),),
    )


def test_usuario_autenticado_sin_ser_revisor_no_escribe(transaccion):
    _sembrar_registro(transaccion)
    usuario = uuid.uuid4()
    _como(transaccion, "authenticated", usuario)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insertar_revision(transaccion, usuario)


def test_revisor_escribe_solo_a_su_nombre(transaccion):
    _sembrar_registro(transaccion)
    revisor = uuid.uuid4()
    transaccion.execute(
        "insert into revisores (usuario_id, nombre) values (%s, 'Revisora')", (str(revisor),)
    )
    _como(transaccion, "authenticated", revisor)
    with transaccion.transaction():
        _insertar_revision(transaccion, revisor)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        _insertar_revision(transaccion, uuid.uuid4())
