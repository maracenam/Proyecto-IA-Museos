import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
MIGRACIONES = sorted((Path(__file__).parents[1] / "db" / "migrations").glob("*.sql"))


def leer_fixture(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def html_ficha(surdoc_id: str) -> str:
    return leer_fixture(f"registro_{surdoc_id}.html")


@pytest.fixture(scope="session")
def conexion_bd():
    """Conexión a un Postgres local con las migraciones aplicadas. Se omite si no hay base.
    Las pruebas que escriben usan `bd`, que revierte todo al terminar."""
    psycopg = pytest.importorskip("psycopg")
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL no definida")
    try:
        con = psycopg.connect(url, autocommit=True)
    except psycopg.OperationalError as error:
        pytest.skip(f"Base no disponible: {error}")
    for archivo in MIGRACIONES:
        con.execute(archivo.read_text(encoding="utf-8"))
    # Datos de referencia que el pipeline carga en cada normalización: sin ellos, una base nueva
    # (como la de CI) rechaza las revisiones por categoría inválida.
    from pipeline.normalize.vocabulario import Vocabulario, sincronizar_vocabulario

    sincronizar_vocabulario(con, Vocabulario.cargar())
    yield con
    con.close()


@pytest.fixture
def bd(conexion_bd):
    """Base vacía para la prueba: se vacían las tablas dentro de una transacción que
    siempre se revierte, así que los datos existentes vuelven intactos al terminar."""
    with conexion_bd.transaction(force_rollback=True):
        conexion_bd.execute(
            "delete from registro_terminos; delete from normalizaciones; delete from revisiones;"
            "delete from embeddings; delete from registros; delete from registros_raw;"
            "delete from cuarentena; delete from ejecuciones;"
        )
        yield conexion_bd
