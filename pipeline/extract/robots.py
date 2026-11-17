"""Evaluación de robots.txt con comodines.

urllib.robotparser de Python solo compara prefijos y no entiende `*` a mitad de ruta
ni `$` al final, así que ignoraría la regla real de SURDOC `Disallow: /registro/*/pdf`.
Aquí se sigue la norma RFC 9309: se aplica el grupo del agente más específico (o `*`),
gana la regla que coincide con más caracteres y, en empate, gana Allow."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _Regla:
    permitir: bool
    patron: str
    expresion: re.Pattern


def _compilar(patron: str) -> re.Pattern:
    anclado = patron.endswith("$")
    cuerpo = patron[:-1] if anclado else patron
    regex = ".*".join(re.escape(parte) for parte in cuerpo.split("*"))
    return re.compile(regex + ("$" if anclado else ""))


class Robots:
    def __init__(self, texto: str):
        self._grupos: dict[str, list[_Regla]] = {}
        agentes: list[str] = []
        en_reglas = False
        for linea in texto.splitlines():
            linea = linea.split("#", 1)[0].strip()
            if ":" not in linea:
                continue
            clave, valor = (p.strip() for p in linea.split(":", 1))
            clave = clave.lower()
            if clave == "user-agent":
                if en_reglas:
                    agentes, en_reglas = [], False
                agentes.append(valor.lower())
                for agente in agentes:
                    self._grupos.setdefault(agente, [])
            elif clave in ("allow", "disallow") and agentes:
                en_reglas = True
                if not valor:
                    continue  # "Disallow:" vacío no prohíbe nada
                regla = _Regla(clave == "allow", valor, _compilar(valor))
                for agente in agentes:
                    self._grupos[agente].append(regla)

    def _reglas_para(self, agente: str) -> list[_Regla]:
        agente = agente.lower()
        candidatos = [g for g in self._grupos if g != "*" and g in agente]
        if candidatos:
            return self._grupos[max(candidatos, key=len)]
        return self._grupos.get("*", [])

    def permitido(self, agente: str, ruta: str) -> bool:
        mejor: _Regla | None = None
        for regla in self._reglas_para(agente):
            if regla.expresion.match(ruta):
                if (
                    mejor is None
                    or len(regla.patron) > len(mejor.patron)
                    or (len(regla.patron) == len(mejor.patron) and regla.permitir)
                ):
                    mejor = regla
        return mejor is None or mejor.permitir
