"""Normalización con un modelo de lenguaje intercambiable.

`Normalizador` es la interfaz; `NormalizadorOllama` la implementación local (sin costo
externo). Para cambiar a otro proveedor basta con otra clase con el mismo método
`proponer` y elegirla con LLM_PROVEEDOR; el resto del pipeline no cambia."""

import json
import os
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from pipeline.normalize.reglas import Caso

DIRECTORIO_PROMPTS = Path(__file__).parents[2] / "prompts"

QUE_CLASIFICAR = {
    "material": ("el material principal", "materiales"),
    "objeto": ("el tipo de objeto", "tipos de objeto"),
    "tecnica": ("la técnica de manufactura", "técnicas"),
    "estado_conservacion": ("el estado de conservación", "estados"),
}


class RespuestaLLM(BaseModel):
    valor: str
    confianza: float = Field(ge=0, le=1)
    justificacion: str


class RespuestaInvalida(Exception):
    """El modelo respondió, pero no con JSON válido o con una categoría que no existe."""


class ModeloNoDisponible(Exception):
    """No hay conexión con el modelo (ej. el PC con Ollama está apagado): se detiene la corrida."""


class Normalizador(Protocol):
    modelo: str

    def proponer(self, sistema: str, mensaje: str, categorias: list[str]) -> RespuestaLLM: ...


class Prompt:
    def __init__(self, version: str, plantilla: str):
        self.version = version
        self.plantilla = plantilla

    @classmethod
    def cargar(cls, version: str = "v1", directorio: Path = DIRECTORIO_PROMPTS) -> "Prompt":
        ruta = directorio / f"normalizar_{version}.md"
        return cls(version, ruta.read_text(encoding="utf-8"))

    def sistema(self, campo: str, categorias: list[tuple[str, str]]) -> str:
        que, que_plural = QUE_CLASIFICAR[campo]
        lista = "\n".join(
            f"- {nombre}: {desc}" if desc else f"- {nombre}" for nombre, desc in categorias
        )
        return self.plantilla.format(
            que_clasificar=que, que_clasificar_plural=que_plural, categorias=lista
        )

    @staticmethod
    def mensaje(caso: Caso) -> str:
        ctx = caso.contexto
        declarado = caso.entrada if caso.origen != "descripcion" else "(la ficha no lo declara)"
        lineas = [
            f"Campo a clasificar: {caso.campo}",
            f"Valor declarado en la ficha: {declarado}",
            f"Objeto: {ctx.get('objeto') or '(sin dato)'}",
            f"Técnica / Material declarado: {ctx.get('tecnica_material') or '(sin dato)'}",
            f"Descripción: {(ctx.get('descripcion') or '(sin descripción)')[:1500]}",
        ]
        return "\n".join(lineas)


class NormalizadorOllama:
    def __init__(
        self,
        modelo: str,
        url: str = "http://localhost:11434",
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.modelo = modelo
        self._http = httpx.Client(base_url=url.rstrip("/"), timeout=timeout, transport=transport)

    def proponer(self, sistema: str, mensaje: str, categorias: list[str]) -> RespuestaLLM:
        esquema = {
            "type": "object",
            "properties": {
                "valor": {"type": "string", "enum": categorias},
                "confianza": {"type": "number", "minimum": 0, "maximum": 1},
                "justificacion": {"type": "string"},
            },
            "required": ["valor", "confianza", "justificacion"],
        }
        try:
            respuesta = self._http.post(
                "/api/chat",
                json={
                    "model": self.modelo,
                    "messages": [
                        {"role": "system", "content": sistema},
                        {"role": "user", "content": mensaje},
                    ],
                    "format": esquema,
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
        except httpx.TransportError as error:
            raise ModeloNoDisponible(f"No se pudo conectar con Ollama: {error!r}") from error
        if respuesta.status_code == 404:
            raise ModeloNoDisponible(
                f"Ollama no tiene el modelo {self.modelo!r}: ejecuta `ollama pull {self.modelo}`"
            )
        if respuesta.status_code != 200:
            raise ModeloNoDisponible(f"Ollama respondió HTTP {respuesta.status_code}")
        try:
            contenido = respuesta.json()["message"]["content"]
            salida = RespuestaLLM.model_validate(json.loads(contenido))
        except (KeyError, json.JSONDecodeError, ValidationError) as error:
            raise RespuestaInvalida(f"JSON inválido: {error}") from error
        if salida.valor not in categorias:
            raise RespuestaInvalida(f"Categoría inexistente: {salida.valor!r}")
        return salida

    def cerrar(self) -> None:
        self._http.close()


def crear_normalizador() -> Normalizador:
    """Normalizador según variables de entorno (LLM_PROVEEDOR, LLM_MODELO, OLLAMA_URL)."""
    proveedor = os.environ.get("LLM_PROVEEDOR", "ollama").lower()
    modelo = os.environ.get("LLM_MODELO", "").strip()
    if not modelo:
        raise SystemExit("Falta LLM_MODELO (ver .env.example).")
    if proveedor == "ollama":
        return NormalizadorOllama(modelo, os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    raise SystemExit(f"Proveedor de LLM no soportado: {proveedor!r}")
