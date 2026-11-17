"""Modelo tipado de una ficha de SURDOC tal como se extrae (capa bronce).

Contiene todos los campos parseados, incluidos los que nunca se publican
(ej. nombre_sitio); la capa plata elige qué columnas exponer."""

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

CampoTermino = Literal["objeto", "nombre_alternativo", "tecnica", "material"]
FuenteTermino = Literal["aat", "tesauro_regional"]
ID_SURDOC = re.compile(r"^\d+-\d+$")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Termino(_Base):
    campo: CampoTermino
    orden: int
    grupo: int | None = None
    texto: str
    fuente: FuenteTermino | None = None
    id_termino: str | None = None

    @field_validator("texto")
    @classmethod
    def _no_vacio(cls, valor: str) -> str:
        if not valor:
            raise ValueError("término sin texto")
        return valor


class Imagen(_Base):
    url: str
    credito: str | None = None


class Ficha(_Base):
    surdoc_id: str
    institucion: int
    titulo: str | None = None
    numero_inventario: str | None = None
    clasificacion: str | None = None
    coleccion: str | None = None
    objeto: str | None = None
    nombre_alternativo: str | None = None
    dimensiones: str | None = None
    tecnica_material: str | None = None
    ubicacion: str | None = None
    situacion: str | None = None
    descripcion: str | None = None
    estado_conservacion: str | None = None
    procedencia: str | None = None
    cultura_originaria: str | None = None
    cultura_arqueologica: str | None = None
    area_cultural: str | None = None
    area_geografica: str | None = None
    nombre_sitio: str | None = None  # dato sensible: solo bronce, nunca se publica
    fecha_creacion: str | None = None
    creador: str | None = None
    forma_ingreso: str | None = None
    fecha_ingreso: str | None = None
    historia_objeto: str | None = None
    historia_propiedad_uso: str | None = None
    terminos: tuple[Termino, ...] = ()
    imagenes: tuple[Imagen, ...] = ()
    # Todas las etiquetas encontradas, para no perder campos que el modelo aún no nombra.
    otros_campos: dict[str, tuple[str, ...]] = {}

    @field_validator("surdoc_id")
    @classmethod
    def _formato_id(cls, valor: str) -> str:
        if not ID_SURDOC.match(valor):
            raise ValueError(f"surdoc_id inválido: {valor!r}")
        return valor

    @field_validator("*", mode="before")
    @classmethod
    def _vacio_a_none(cls, valor):
        if isinstance(valor, str) and not valor.strip():
            return None
        return valor

    def campos(self) -> dict:
        """Campos parseados en forma JSON, lo que se guarda en registros_raw.campos."""
        return self.model_dump(mode="json")

    def hash_campos(self) -> str:
        """sha256 de los campos parseados en orden estable. Nunca se hashea el HTML,
        que trae atributos dinámicos (data-b-token, itok=, data-once)."""
        texto = json.dumps(self.campos(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()
