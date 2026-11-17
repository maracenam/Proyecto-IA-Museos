"""Configuración del pipeline, leída de variables de entorno (ver .env.example)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

PAUSA_MINIMA_SEGUNDOS = 2.0  # RNF-01: máximo 1 solicitud cada 2 segundos


@dataclass(frozen=True)
class Config:
    database_url: str
    surdoc_base_url: str
    surdoc_user_agent: str
    surdoc_pausa_segundos: float


def cargar_config() -> Config:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("Falta DATABASE_URL (ver .env.example).")
    user_agent = os.environ.get("SURDOC_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit("Falta SURDOC_USER_AGENT: debe identificar el proyecto y un contacto.")
    return Config(
        database_url=database_url,
        surdoc_base_url=os.environ.get("SURDOC_BASE_URL", "https://www.surdoc.cl").rstrip("/"),
        surdoc_user_agent=user_agent,
        surdoc_pausa_segundos=max(
            float(os.environ.get("SURDOC_PAUSA_SEGUNDOS", PAUSA_MINIMA_SEGUNDOS)),
            PAUSA_MINIMA_SEGUNDOS,
        ),
    )
