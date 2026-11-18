"""Acceso a datos de la app.

La app nunca tiene una clave que le permita escribir por su cuenta:
- `FuenteSupabase` (producción) lee con la clave pública (anon), así que RLS aplica siempre.
  Para revisar, la revisora inicia sesión en Supabase Auth y la corrección se guarda con su
  token; la base verifica que esté en `revisores`.
- `FuentePostgres` (desarrollo local) lee del Postgres de docker compose cambiando al rol
  `anon` o `authenticated` en cada consulta, para que RLS se comporte igual que en Supabase.
"""

import os
from dataclasses import dataclass
from typing import Protocol

import httpx

VISTAS = ("fichas_publicas", "valor_vigente", "cola_revision", "categorias", "parametros")


class ErrorSesion(Exception):
    """No se pudo iniciar sesión."""


class ErrorEscritura(Exception):
    """La base rechazó la revisión (sin permiso o valor inválido)."""


@dataclass(frozen=True)
class Sesion:
    usuario_id: str
    correo: str
    token: str


class FuenteDatos(Protocol):
    def leer(self, vista: str) -> list[dict]: ...

    def buscar(self, vector: str, modelo: str, limite: int = 10) -> list[dict]: ...

    def iniciar_sesion(self, correo: str, clave: str) -> Sesion: ...

    def guardar_revision(
        self, sesion: Sesion, surdoc_id: str, campo: str, orden: int,
        valor_anterior: str | None, valor_corregido: str,
    ) -> None: ...  # fmt: skip


class FuenteSupabase:
    def __init__(self, url: str, clave_anon: str, transport: httpx.BaseTransport | None = None):
        self.clave_anon = clave_anon
        self._http = httpx.Client(base_url=url.rstrip("/"), timeout=20.0, transport=transport)

    def _cabeceras(self, token: str | None = None) -> dict[str, str]:
        return {"apikey": self.clave_anon, "Authorization": f"Bearer {token or self.clave_anon}"}

    def leer(self, vista: str) -> list[dict]:
        if vista not in VISTAS:
            raise ValueError(f"Vista desconocida: {vista}")
        respuesta = self._http.get(
            f"/rest/v1/{vista}", params={"select": "*"}, headers=self._cabeceras()
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def buscar(self, vector: str, modelo: str, limite: int = 10) -> list[dict]:
        """Llama a la función buscar_fichas (RPC) con la clave pública."""
        respuesta = self._http.post(
            "/rest/v1/rpc/buscar_fichas",
            json={"consulta": vector, "modelo_busqueda": modelo, "limite": limite},
            headers=self._cabeceras(),
        )
        respuesta.raise_for_status()
        return respuesta.json()

    def iniciar_sesion(self, correo: str, clave: str) -> Sesion:
        respuesta = self._http.post(
            "/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": correo, "password": clave},
            headers={"apikey": self.clave_anon},
        )
        if respuesta.status_code != 200:
            raise ErrorSesion("Correo o contraseña incorrectos.")
        datos = respuesta.json()
        return Sesion(
            datos["user"]["id"], datos["user"].get("email", correo), datos["access_token"]
        )

    def guardar_revision(
        self, sesion, surdoc_id, campo, orden, valor_anterior, valor_corregido
    ) -> None:
        respuesta = self._http.post(
            "/rest/v1/revisiones",
            json={
                "surdoc_id": surdoc_id,
                "campo": campo,
                "orden": orden,
                "valor_anterior": valor_anterior,
                "valor_corregido": valor_corregido,
            },  # fmt: skip
            headers={**self._cabeceras(sesion.token), "Prefer": "return=minimal"},
        )
        if respuesta.status_code in (200, 201, 204):
            return
        if respuesta.status_code in (401, 403):
            raise ErrorEscritura("Tu usuario no está autorizado como revisor.")
        if respuesta.status_code == 409:
            raise ErrorEscritura(f"«{valor_corregido}» no es una categoría válida para {campo}.")
        raise ErrorEscritura(f"La base rechazó la revisión (HTTP {respuesta.status_code}).")


class FuentePostgres:
    """Solo para desarrollo local. La sesión de revisión se simula con REVISOR_LOCAL_CORREO y
    REVISOR_LOCAL_ID; la escritura igual pasa por RLS como usuario `authenticated`."""

    def __init__(
        self,
        url: str | None = None,
        correo_revisor: str | None = None,
        id_revisor: str | None = None,
        con=None,
    ):
        import psycopg  # solo se necesita en desarrollo

        self._psycopg = psycopg
        self.con = con or psycopg.connect(url, autocommit=True)
        self.correo_revisor = correo_revisor
        self.id_revisor = id_revisor

    def _como(self, rol: str, usuario_id: str | None = None):
        self.con.execute(f"set local role {rol}")
        if usuario_id:
            self.con.execute("select set_config('request.jwt.claim.sub', %s, true)", (usuario_id,))

    def _restaurar(self):
        self.con.execute("reset role")
        self.con.execute("select set_config('request.jwt.claim.sub', '', true)")

    def leer(self, vista: str) -> list[dict]:
        if vista not in VISTAS:
            raise ValueError(f"Vista desconocida: {vista}")
        with (
            self.con.transaction(),
            self.con.cursor(row_factory=self._psycopg.rows.dict_row) as cur,
        ):
            self._como("anon")
            filas = cur.execute(f"select * from {vista}").fetchall()  # vista validada arriba
            # Si la consulta falla, el rollback deshace el cambio de rol; aquí, el caso feliz.
            self._restaurar()
        return [
            {k: (float(v) if type(v).__name__ == "Decimal" else v) for k, v in f.items()}
            for f in filas
        ]

    def buscar(self, vector: str, modelo: str, limite: int = 10) -> list[dict]:
        with (
            self.con.transaction(),
            self.con.cursor(row_factory=self._psycopg.rows.dict_row) as cur,
        ):
            self._como("anon")
            filas = cur.execute(
                "select * from buscar_fichas(%s::extensions.vector, %s, %s)",
                (vector, modelo, limite),
            ).fetchall()
            self._restaurar()
        return filas

    def iniciar_sesion(self, correo: str, clave: str) -> Sesion:
        if not self.correo_revisor or not self.id_revisor or correo != self.correo_revisor:
            raise ErrorSesion("Correo o contraseña incorrectos.")
        return Sesion(self.id_revisor, correo, "local")

    def guardar_revision(
        self, sesion, surdoc_id, campo, orden, valor_anterior, valor_corregido
    ) -> None:
        try:
            with self.con.transaction():
                self._como("authenticated", sesion.usuario_id)
                self.con.execute(
                    """insert into revisiones
                       (surdoc_id, campo, orden, valor_anterior, valor_corregido)
                       values (%s, %s, %s, %s, %s)""",
                    (surdoc_id, campo, orden, valor_anterior, valor_corregido),
                )
                self._restaurar()  # si falla, el rollback ya deshace el cambio de rol
        except self._psycopg.errors.InsufficientPrivilege as error:
            raise ErrorEscritura("Tu usuario no está autorizado como revisor.") from error
        except self._psycopg.errors.ForeignKeyViolation as error:
            raise ErrorEscritura(
                f"«{valor_corregido}» no es una categoría válida para {campo}."
            ) from error


def crear_fuente(config: dict[str, str | None]) -> FuenteDatos:
    """Supabase si hay SUPABASE_URL y SUPABASE_ANON_KEY; si no, Postgres local (DATABASE_URL)."""
    if config.get("SUPABASE_URL") and config.get("SUPABASE_ANON_KEY"):
        return FuenteSupabase(config["SUPABASE_URL"], config["SUPABASE_ANON_KEY"])
    if config.get("DATABASE_URL"):
        return FuentePostgres(
            config["DATABASE_URL"],
            config.get("REVISOR_LOCAL_CORREO"),
            config.get("REVISOR_LOCAL_ID"),
        )
    raise RuntimeError("Configura SUPABASE_URL y SUPABASE_ANON_KEY (o DATABASE_URL en desarrollo).")


def leer_config(secretos: dict | None = None) -> dict[str, str | None]:
    claves = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "DATABASE_URL",
              "REVISOR_LOCAL_CORREO", "REVISOR_LOCAL_ID", "EMBEDDING_MODELO")  # fmt: skip
    secretos = secretos or {}
    return {k: secretos.get(k) or os.environ.get(k) for k in claves}
