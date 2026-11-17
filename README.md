# Observatorio de Colecciones Arqueológicas SURDOC

Pipeline que convierte las fichas arqueológicas públicas de [SURDOC](https://www.surdoc.cl) en un dataset normalizado, consultable y trazable, con un dashboard y búsqueda en lenguaje natural. La IA corre en local (Ollama), sin costos externos.

- Diseño técnico: [`DISENO_TECNICO.md`](DISENO_TECNICO.md)
- Contexto y reglas del proyecto: [`CLAUDE.md`](CLAUDE.md)
- Hallazgos del Sprint 0: [`docs/sprint0.md`](docs/sprint0.md)

## Estado

| Sprint | Objetivo | Estado |
|---|---|---|
| 0 | Preparación y descubrimiento | En curso: falta Supabase y elegir el modelo local |
| 1 | Extracción | — |
| 2 | Normalización | — |
| 3 | Dashboard y revisión (MVP) | — |
| 4 | Búsqueda semántica | — |
| 5 | Escala y portafolio | — |

MVP: Museo Regional de Magallanes, clasificación Antropología, Arqueología y Etnografía (77 fichas).

## Desarrollo local

Requisitos: Docker y [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up -d          # Postgres + pgvector con las migraciones aplicadas
uv sync                       # dependencias (Python 3.12)
uv run ruff check .
DATABASE_URL=postgresql://observatorio:observatorio@localhost:5432/observatorio uv run pytest
```

Ollama, opcional en local: `docker compose --profile ia up -d`.

## Fuente y atribución

Los datos provienen de SURDOC (Servicio Nacional del Patrimonio Cultural) y de cada institución. Cada registro enlaza a su ficha original. Las fotografías no se descargan ni se republican, y nunca se publican sitios arqueológicos ni ubicaciones exactas.
